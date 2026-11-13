# Developer Guide

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python dependency manager
- [GNU Make](https://www.gnu.org/software/make/) — task runner (`make help` lists every target; preinstalled on macOS and most Linux distributions)
- [jq](https://jqlang.org/) — JSON CLI tool, used by the caveman hooks (see [Claude Code](#claude-code))

## First-time setup

```bash
cp .env.example .env
# Set SECRET_KEY to a long random string in .env

uv sync
uv run pre-commit install   # git hooks: commit message format, and make qa on Python changes
make bootstrap
```

The hooks are what check each commit message against Conventional Commits
before it reaches CI; CI checks the PR title, which becomes the squash-merge
subject on `main`.

`make bootstrap` applies migrations and creates the owner: one superuser
(the only account that can log in, including at `/admin/`). It reads
`DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL` and
`DJANGO_SUPERUSER_PASSWORD` from the environment or `.env`, and prompts for any
that are blank. There are no defaults. The password must pass Django's password
validators, so a short or guessable one is refused. If the username already
exists it does nothing, so it is safe to re-run; it never changes an existing
password. To change one, run `make manage ARGS="changepassword <username>"`.

On a server, prefer the prompt or a one-off environment variable over writing
the password into `.env`, and pass `--noinput` to the command
(`uv run python manage.py bootstrap_owner --noinput`) to fail instead of
prompting when a variable is missing.

## Running the app

```bash
make dev               # port 8987
make dev PORT=9000     # custom port
```

Opens at <http://127.0.0.1:8987/recipes/>.

## The database

`db.sqlite3` is the only copy of the data. A fresh checkout starts empty:
`make bootstrap` (see *First-time setup*) creates the tables and the owner.

### Demo data

To try the ingredient clean-up tool or review a UI change without typing
recipes in by hand:

```bash
make seed                            # four sample recipes for the user 'demo'
make seed ARGS="--username <name>"   # the same recipes in an existing account
make seed ARGS="--reset"             # delete the demo recipes and seed them again
```

`make seed` applies migrations, then runs the `seed_demo` command. If the user
does not exist it is created as staff (so the ingredient and cuisine tools
open) with a random password, printed once; change it with
`make manage ARGS="changepassword demo"`. An existing account is used as it
is: its password and staff flag are not touched.

The recipes cover the cases that are tedious to build: singular/plural
duplicates (`onion`/`onions`, `chilli`/`chillies`), a private `Onion` beside
the global `onion`, a spelling variant (`aubergine`/`eggplant`), private
ingredients to promote, an unused ingredient (`saffron`), plural overrides,
one unnamed and several named ingredient groups, substitutes, titled and
untitled steps, inline tags in titles and blurbs, global and private tags,
and cuisines at every depth.

Running it again adds only the recipes that are missing. Once the clean-up
tool has merged the duplicates away, `--reset` brings them back. The command
refuses to run under `nutrisho.settings.prod`, which is what a bare
`uv run python manage.py` uses.

### Concurrent writes

`base.py` sets three SQLite options (issue #38), because Django's defaults let
two overlapping saves fail with `database is locked`:

- `transaction_mode: IMMEDIATE` — every `atomic()` block takes the write lock
  when it starts, so a second writer waits instead of failing.
- `timeout: 20` — how long a writer waits for the lock, in seconds.
- `PRAGMA journal_mode=WAL` — readers keep going while someone writes. Changes
  go to `db.sqlite3-wal` first and are copied into `db.sqlite3` later (a
  *checkpoint*); `db.sqlite3-shm` is its index. All three files are one
  database. `PRAGMA synchronous=NORMAL` is the usual WAL pairing: the database
  can never be corrupted, but a power cut or OS crash (not an app crash) can
  undo the last moments of saves.

Options in `DATABASE_URL` (for example `?timeout=5`) override these. The tests
run with the same options on a temporary file, so
`tests/recipes/test_concurrent_writes.py` exercises real SQLite locking.

Rules that follow from WAL:

- Never delete `db.sqlite3-wal` or `db.sqlite3-shm` while the database is in
  use, and never move `db.sqlite3` without them: committed changes may still
  be in the `-wal` file.
- Do not back up by copying `db.sqlite3` alone. `make backup` reads
  through SQLite, sees everything, and dumps one consistent snapshot even
  while the app is saving. For a file copy, use
  `sqlite3 db.sqlite3 ".backup copy.sqlite3"`, or stop the app first.
- Keep the database on a local disk; WAL does not work on network file systems.
- When restoring or replacing `db.sqlite3`, stop the app and remove the old
  `-wal` and `-shm` files with it, so they are not paired with the wrong file.

### Switching an existing database to WAL

Nothing in the data changes: WAL is a different way of writing the same file,
and the first connection after deploying converts it in place. Once:

1. Stop the app and take a backup (`make backup`, plus
   `cp db.sqlite3 db.sqlite3.pre-wal` — safe while stopped).
2. Deploy and start the app. Check the mode:
   `sqlite3 db.sqlite3 "PRAGMA journal_mode;"` prints `wal`.
3. Update any backup script that copies `db.sqlite3` to follow the rules above.

To go back: stop the app, revert the settings (otherwise the next connection
switches to WAL again), and run `sqlite3 db.sqlite3 "PRAGMA journal_mode=DELETE;"`,
which folds the `-wal` file back into `db.sqlite3` and removes it.

To delete recipes by ID:

```bash
make manage ARGS="delete_recipe --id 42"
make manage ARGS="delete_recipe --id 42 43 44"
```

## Backing up

```bash
make backup    # schema + full dump
make schema    # migrate, then schema only
```

`backup_db` writes two files:

- `docs/schema.sql` — `CREATE` statements only, sorted so the file changes only
  when the schema does. **Committed.** Regenerate it with `make schema` in any PR
  that adds a migration (see [AGENTS.md](../AGENTS.md)).
- `docs/dump-<timestamp>.sql` — schema and every row. **Git-ignored**
  (`docs/dump-*`), since it holds the data. Restore into an empty database with
  `sqlite3 db.sqlite3 < docs/dump-<timestamp>.sql`, with the app stopped and
  any old `db.sqlite3-wal`/`-shm` files moved aside with the old database.

`--schema PATH` and `--dump PATH` override either location. SQLite only.

`make check-migrations` (part of `make qa`) keeps both honest: it migrates a
throwaway SQLite database, fails if `makemigrations --check` finds a model
change with no migration, then writes that database's schema to a temp file and
diffs it against `docs/schema.sql`. It never touches `db.sqlite3`.

## Errors and outages in production

All logging goes to stderr; under systemd, journald collects it
(`journalctl -u <service>`). That covers 500s with their tracebacks, CSRF
rejections and other `django.security` events, and failed logins (a warning on
`recipes.auth` with the username and client IP, never the password).

- `LOG_LEVEL` — level for the `django`, `recipes` and `nutrisho` loggers;
  default `INFO`. `django.security` always logs at `WARNING` or above, so a
  quiet level cannot hide it.
- `SENTRY_DSN` — optional. When set, `settings/prod.py` initialises Sentry, which
  reports unhandled exceptions and `ERROR` log records. Personal data is not
  sent. Unset, Sentry is never initialised.

`GET /healthz` is unauthenticated and never cached. It runs `SELECT 1` and
answers `200 ok`, or `503 database unavailable` (and logs an error) when the
database does not respond. Point the deploy smoke check and a free external
uptime monitor at `https://<host>/healthz`. The backup timer gets its own
healthchecks.io ping with the backup job (#44).

## Quality checks

```bash
make qa                      # lint + typecheck + migrations + tests with coverage
make lint                    # ruff only
make typecheck               # ty only
make check-migrations        # no missing migration, docs/schema.sql up to date
make test                    # pytest, no coverage: the fast TDD loop
make test ARGS="tests/test_healthz.py -k healthz"  # a path or other arguments go to pytest
make test-cov                # pytest with line and branch coverage (≥95% required)
make coverage                # open the HTML report from the last make test-cov
make audit                   # known vulnerabilities in uv.lock
make e2e                     # browser smoke tests in Chromium
```

`make test` prints one line of dots and the short tracebacks of any failures,
so it suits a single file or test; add `ARGS="-v"` for test names. The 95% gate
lives in `make test-cov`, because a subset of the suite never reaches it.
`make qa` needs no network. There is no build step for the front end: the
stylesheets and `app.js` are served as written.

Tests run with `--fail-on-template-vars`, so a template that uses an undefined
variable fails the test instead of rendering an empty string. Every directory
under `src/` is a package (`tests/test_project_config.py` checks it), so
coverage reports every module, tested or not.

`make e2e` runs the browser smoke tests in `tests/recipes/e2e/`, which drive
the app in Chromium (see [Browser tests](features/browser-code-and-csp.md#browser-tests-63)).
They need a browser, installed once with `uv run playwright install chromium`,
so plain pytest, `make test` and `make qa` skip them. Add `ARGS="--headed"` to
watch them, or `ARGS="--tracing retain-on-failure"` for a trace of a failure.

`make audit` needs the network, so it is not part of `make qa`. It runs
`pip-audit` over `uv export --all-groups` and fails on any advisory. CI runs it in
the `Audit` workflow on every PR, on pushes to `main`, and every Monday, so a
new advisory against an unchanged lockfile still shows up.

## CI

The `CI` workflow (`.github/workflows/ci.yml`) installs from the lockfile
(`uv sync --locked`), so a `uv.lock` that is out of date with `pyproject.toml`
fails the build, then runs `make qa`. On `main` it also runs `make coverage-badge`,
which writes the coverage total as a shields.io endpoint JSON, and a separate
`badge` job publishes that file to the `badges` branch for the README badge,
and a `release` job publishes a new version (see [Releases](#releases)).
An `e2e` job installs Chromium and runs `make e2e` beside `qa`, uploading a
screenshot of any failed browser test.

The `PR title` workflow (`.github/workflows/pr-title.yml`) runs `cz check` on
the PR title whenever a PR is opened, pushed to or retitled, because the title
becomes the squash-merge subject on `main` and no commit hook sees it.

Every workflow follows the same rules, and `tests/test_workflows.py` checks
them:

- The token is read-only; only the `badge` and `release` jobs get
  `contents: write`, and neither runs project code.
- Every action is pinned to a commit SHA with a `# vX.Y.Z` comment, which
  Dependabot updates together. The uv version is pinned in the `setup-uv`
  step; pnpm's comes from `packageManager` in `package.json`.
- Every job has a `timeout-minutes`, and a newer push to a PR cancels the
  run it replaces.
- Nothing is installed with `pip` or `apt-get`.

## Releases

The version lives in `pyproject.toml` (and its copy in `uv.lock`); it is the
only version number, so `package.json` has none. Each release is tagged
`v<version>` on `main` and has a GitHub release whose notes are its section of
[`CHANGELOG.md`](../CHANGELOG.md). Deploy a tag, not a branch: the tag answers
"what is running", and rolling back is checking out the previous tag.

Commitizen (`[tool.commitizen]` in `pyproject.toml`) works out the next
version from the Conventional Commit subjects on `main` since the last tag:
a `feat` bumps the minor version, a `fix` or `perf` the patch. Until 1.0 a
breaking change bumps the minor version too (`major_version_zero`).

`main` only takes squash-merged PRs, so a release is a PR:

1. `make release` on a clean checkout. It fetches `main` and its tags, makes
   a `chore-release-v<next>` branch off `origin/main`, runs
   `cz bump --version-files-only`, which writes the new version to
   `pyproject.toml` and `uv.lock` and adds its section to `CHANGELOG.md`, and
   commits that as `chore(release): v<next>`. It stops if there is nothing to
   release (only `chore`, `docs`, `test` and similar commits since the last
   tag).
2. Read the new `CHANGELOG.md` section and edit it if a line needs it, then
   push the branch and open a PR titled `chore(release): v<next>`.
3. When it merges, the CI `release` job sees a version with no release yet,
   tags the merge commit `v<next>` and publishes the GitHub release. Pushes
   that leave the version alone do nothing there.

Never edit the version by hand: `cz bump` keeps `pyproject.toml`, `uv.lock`
and `CHANGELOG.md` in step, and `tests/test_releases.py` checks they agree.

## Dependency updates

Dependabot (`.github/dependabot.yml`) opens update PRs for four ecosystems:
uv, npm (pnpm) and GitHub Actions weekly, and pre-commit hook revs
monthly. Minor and patch bumps arrive grouped into one PR per ecosystem; a
major bump gets its own PR. Review them like any other PR: CI must be green,
and a `uv.lock` change that touches Django follows the
[version policy](#django-version-policy) below.

`make` on its own, or `make help`, lists every target with a one-line
description. A target appears there when its rule line in the `Makefile` ends
in a `## description` comment, so add one to every new target.

## Management commands

`manage.py` defaults to the production settings, which need a `SECRET_KEY` and
turn `DEBUG` off, so on a development machine run management commands through
make, which uses the dev settings:

```bash
make manage ARGS="check"
make manage ARGS="changepassword <username>"
```

Calling `uv run python manage.py …` directly is for the server, where the
production settings are the point.

## CSS

Plain CSS, no framework and no build step (#76): `src/recipes/static/css/style.css`
for the screen and `print.css` for print, served as written. Most of it styles
HTML elements directly, so a template needs few classes. The look and its
colours are described in [the design note](features/design.md).

## Tech stack

| Concern | Tool |
|---|---|
| Language | Python 3.14 |
| Framework | Django 6.1 |
| Database | SQLite |
| Python deps | uv |
| Lint | ruff |
| Types | ty |
| Tests | pytest + pytest-django |
| Tasks | GNU Make (`Makefile`) |
| CSS | Plain CSS, no build step |
| HTMX | django-htmx |

### Django version policy

`pyproject.toml` pins `Django ~=6.1`, which allows any 6.x release from 6.1
on, and `uv.lock` holds the exact version. Each feature release only gets
security fixes for a limited time, so the pin has to move on purpose:

- **Now:** 6.1. Its security support runs out around December 2027.
- **Spring 2027:** move to 6.2, the next long-term support (LTS) release,
  due around April 2027. That is also when 6.0 loses security support.
- **After that:** stay on LTS releases and plan each move before the current
  one's support ends.

Before an upgrade, run the suite with deprecations turned into errors so
anything the new release removes shows up first:

```bash
DJANGO_SETTINGS_MODULE=nutrisho.settings.test uv run pytest -W error::DeprecationWarning -W error::PendingDeprecationWarning
```

Then bump the pin, refresh the lock with
`uv lock --upgrade-package django`, and run `make qa`.

## Project layout

```
src/
  nutrisho/      # Django project (settings, urls, wsgi, health check)
  recipes/       # Main app: models, views, templates, management commands
docs/
  features/            # one note per feature area: design and pitfalls
  schema.sql           # current DB schema (generated by backup_db)
  developer-guide.md   # this file
  plans/               # active work plans
  archive/             # completed plans
  reviews/             # raw review and assessment reports
tests/
  conftest.py
  recipes/
```

## Claude Code

`.claude/settings.json` holds a permission allowlist for the `make`, `uv run`
and read-only `git` commands AGENTS.md asks for, and a `startup` hook that
reminds the assistant to confirm the branch. Project skills live in
`.claude/skills/<name>/SKILL.md`; `tdd` is the one AGENTS.md mandates.

It also turns on caveman mode (terse replies, a status-line badge) for every
session, re-injecting its rules after each compaction. The hooks need `jq`
and keep their state in `~/.claude/.caveman-active`; "stop caveman" or
`/caveman off` turns it off for a session. `make test-hooks` runs their
regression tests; it is not part of `make qa`. Put personal overrides in the
git-ignored `.claude/settings.local.json`.

## Architecture notes

The architecture summary, boundaries and invariants are in the Architecture
section of [AGENTS.md](../AGENTS.md); each feature area has a note in
[docs/features/](features/).

## Workflow

TDD: red → green → refactor. See [AGENTS.md](../AGENTS.md) for the full required flow.

## Branches and commits

Branch names, commit messages and PR titles follow
[AGENTS.md](../AGENTS.md#branches): branches are `[<issue>-]<type>-<slug>`
(`24-feature-pluralise`), commits and PR titles are Conventional Commits.
Run `make qa` before opening a PR.
