# Developer Guide

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python dependency manager
- [poethepoet](https://poethepoet.natn.io/) — task runner (installed by `uv sync`; run as `uv run poe <task>`)
- [pnpm](https://pnpm.io/) — Node dependency manager (for Tailwind CSS)
- [jq](https://jqlang.org/) — JSON CLI tool (`brew install jq`)

## First-time setup

```bash
cp .env.example .env
# Set SECRET_KEY to a long random string in .env

uv sync
pnpm install
pnpm css          # compile Tailwind CSS
```

## Running the app

```bash
uv run poe dev          # port 8987
uv run poe dev 9000     # custom port
```

Opens at <http://127.0.0.1:8987/recipes/>.

## The database

`db.sqlite3` is the only copy of the data. A fresh checkout starts empty:

```bash
uv run poe migrate
python manage.py addinitialuser
```

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
- Do not back up by copying `db.sqlite3` alone. `uv run poe backup` reads
  through SQLite and sees everything. For a file copy, use
  `sqlite3 db.sqlite3 ".backup copy.sqlite3"`, or stop the app first.
- Keep the database on a local disk; WAL does not work on network file systems.
- When restoring or replacing `db.sqlite3`, stop the app and remove the old
  `-wal` and `-shm` files with it, so they are not paired with the wrong file.

### Switching an existing database to WAL

Nothing in the data changes: WAL is a different way of writing the same file,
and the first connection after deploying converts it in place. Once:

1. Stop the app and take a backup (`uv run poe backup`, plus
   `cp db.sqlite3 db.sqlite3.pre-wal` — safe while stopped).
2. Deploy and start the app. Check the mode:
   `sqlite3 db.sqlite3 "PRAGMA journal_mode;"` prints `wal`.
3. Update any backup script that copies `db.sqlite3` to follow the rules above.

To go back: stop the app, revert the settings (otherwise the next connection
switches to WAL again), and run `sqlite3 db.sqlite3 "PRAGMA journal_mode=DELETE;"`,
which folds the `-wal` file back into `db.sqlite3` and removes it.

To delete recipes by ID:

```bash
python manage.py delete_recipe --id 42
python manage.py delete_recipe --id 42 43 44
```

## Backing up

```bash
uv run poe backup                                   # schema + full dump
uv run python manage.py backup_db --schema-only     # schema only
```

`backup_db` writes two files:

- `docs/schema.sql` — `CREATE` statements only, sorted so the file changes only
  when the schema does. **Committed.** Regenerate it with `--schema-only` in any
  PR that adds a migration (see [AGENTS.md](../AGENTS.md)).
- `docs/dump-<timestamp>.sql` — schema and every row. **Git-ignored**
  (`docs/dump-*`), since it holds the data. Restore into an empty database with
  `sqlite3 db.sqlite3 < docs/dump-<timestamp>.sql`, with the app stopped and
  any old `db.sqlite3-wal`/`-shm` files moved aside with the old database.

`--schema PATH` and `--dump PATH` override either location. SQLite only.

## Quality checks

```bash
uv run poe qa        # lint + typecheck + tests + hook regression tests
uv run poe lint      # ruff only
uv run poe typecheck # ty only
uv run poe test      # pytest with coverage (≥95% required)
```

## CSS

Tailwind CSS v4. Source: `src/recipes/static/css/tailwind.css`. Output is a build artifact — not committed.

```bash
pnpm css         # build once (minified)
pnpm css:watch   # rebuild on change
```

Or via poe:

```bash
uv run poe css
uv run poe css-watch
```

## Tech stack

| Concern | Tool |
|---|---|
| Language | Python 3.14 |
| Framework | Django 6.0 |
| Database | SQLite |
| Python deps | uv |
| Lint | ruff |
| Types | ty |
| Tests | pytest + pytest-django |
| Tasks | poethepoet |
| CSS | Tailwind CSS v4 (pnpm) |
| HTMX | django-htmx |

## Project layout

```
src/
  nutrisho/      # Django project (settings, urls, wsgi)
  recipes/       # Main app: models, views, templates, management commands
docs/
  initial-context.md   # architecture and constraints
  schema.sql           # current DB schema (generated by backup_db)
  developer-guide.md   # this file
  plans/               # active work plans
  archive/             # completed plans
tests/
  conftest.py
  recipes/
```

## Architecture notes

See [docs/initial-context.md](initial-context.md) for full architecture, key models, and constraints.

## Workflow

TDD: red → green → refactor. See [AGENTS.md](../AGENTS.md) for the full required flow.

## Branches and commits

- `feature/<name>` / `fix/<name>`
- Imperative present tense, subject ≤ 72 chars
- Small atomic commits
- Run `uv run poe qa` before opening a PR
