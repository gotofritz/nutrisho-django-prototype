# AGENTS.md

## Read First

- `README.md` — project overview
- The Architecture section below; the `server/docs/features/` note for the
  area you are changing
- `docs/plans/*.md` — active plans

## Project Rules

- Use `gh` for all GitHub operations
- Use `make` for workflow discovery (`make help` lists every target); tasks live in `Makefile`
- Run commands from project root

## Repository Layout

Two parts, released and checked separately (#145):

- `server/` — the Django app: a self-contained uv project with its own
  `pyproject.toml`, `uv.lock`, `CHANGELOG.md`, `docs/features/` and
  `docs/schema.sql`
- `extension/` — the recipe clipper browser extension; no code yet, see
  `extension/README.md`. Don't add extension code outside it

The top-level `Makefile` serves both. Server targets keep their plain names
(`make qa`, `make test`) and run inside `server/`, so a path in `ARGS` is
relative to `server/` (`make test` also accepts `server/tests/...`). Run any
other uv command in `server/`, or as `uv run --directory server <cmd>`.
Extension targets will be prefixed `ext-`.

Workflows are per part and path-filtered: the server's skip changes under
`extension/**` alone. Release tags are `server-v<version>` and
`ext-v<version>`. Repo-wide files (`.github/`, `.claude/`, `AGENTS.md`,
`.pre-commit-config.yaml`, `docs/`) stay at the root.

## Plans

- Active: `docs/plans/`
- Archive: `docs/archive/`
- Archive completed plans in the same PR
- Archived filename format: `YYYY-MM-DD-HHMM-<shortsha>-<original-name>.md`
  where date/time and SHA are from the commit that archives the plan
  Example: `2026-05-24-2013-8a8c2cf-002-htmx-tailwind.md`

## Architecture

Paths in this section are relative to `server/`.

Multi-user Django recipe manager, prototype quality. One app, `recipes`, under
`src/`; server-rendered templates with HTMX partial swaps (django-htmx), no
REST API; plain CSS with no build step; SQLite in WAL mode with IMMEDIATE
transactions, and no other database. Auth is Django's `User`; the owner
superuser comes from `make bootstrap`, never from credentials in the repo. The
debug toolbar is a dev-group package, mounted only when installed.

### Boundaries

- `src/nutrisho/` — project config only (settings `base`/`dev`/`prod`/`test`,
  middleware, `/healthz`); no business logic
- `src/recipes/` — all domain logic
  - `services/` — pure query and mutation functions; no HTTP, no templates,
    no forms. Move domain logic here as you touch it, so a command or importer
    can reuse it
  - `utils/` — framework-free helpers
  - `views/` — thin: parse the request, guard, call a service, choose the
    partial. `urls.py` imports each view module directly; there is no
    re-export list in `views/__init__.py`
  - `management/commands/` — management commands
- `tests/` mirrors `src/`

### Invariants

Easy to break, and not obvious from any one file:

- Login is required by default (`HtmxLoginRequiredMiddleware`). A public view
  needs `@login_not_required` and an entry in `PUBLIC_ROUTES` in
  `tests/test_route_access.py`; a new path parameter needs a value in that
  test's `path_values` fixture.
- The recipe page opens in read mode (`reading`, #58), which leaves every
  editing control out; `?edit=1` is edit mode. Partial endpoints never set
  `reading`, so a display partial renders editable unless told otherwise.
- Load a recipe with `owned_recipe(request=..., recipe_id=...)` and its child
  rows through it. Never look a recipe up by id alone.
- Deleting a recipe moves it to the trash (`Recipe.deleted_at`, #75). Anything
  a user sees reads `Recipe.objects.live()` (`owned_recipe` does); only the trash
  page, `restore` and `purge` read `trashed()`. A bulk write by cuisine or
  ingredient covers trashed recipes too, so a restore finds them consistent.
- A clean-up tool action that deletes ingredients runs inside
  `journaled(user=...)` and passes its `Journal` down, noting each write before
  it makes it (`services/ingredient_journal.py`), so Undo can take it back.
- A route that changes a global row (ingredient, tag, cuisine) is staff-only
  (`htmx_staff_required`); its tests use the `other_user` fixture to show a
  non-staff user is refused and nothing is written.
- Typed ingredient, tag and cuisine names become rows only through
  `services/name_resolution.py`. Names are unique ignoring case, so a raw
  `get_or_create(name=...)` fails.
- A typed unit becomes `IngredientInRecipe.unit` only through `find_unit`,
  which never creates one; units and their aliases are staff-curated in admin.
  Free text from before #67 waits in `legacy_unit` for `normalise_units`.
- `index_in_sequence` changes only through `utils/sequencing.py`.
- A response that walks a recipe's groups or rows renders a recipe from
  `with_ingredients` or a group from `with_rows` (`services/recipe_contents.py`),
  called after its writes; otherwise its query count grows with the recipe.
  A new such endpoint gets a case in `tests/recipes/test_query_counts.py`.
- Recipe names and descriptions are written through `Recipe.save()`, which keeps
  `plain_name`/`plain_description` current; a queryset `update()` or
  `bulk_create` leaves them stale.
- Plurals, scaled quantities and HTML sanitising happen at render time. The
  database holds the canonical singular, the stored quantity and markup as typed.
- `IngredientInRecipe.ingredient` and `.substitute` are both `PROTECT`: repoint
  both before deleting an ingredient.
- Empty text fields are stored as `""`, never `NULL`.
- No inline JavaScript or CSS (the CSP forbids it, and
  `tests/test_content_security_policy.py` checks every template): behaviour goes
  in `static/js/app.js` behind `data-*` attributes, and there is no `hx-on` and
  no `hx-trigger` filter. Every asset, fonts included, is self-hosted.
- Write paths read and write inside `atomic()`; SQLite's IMMEDIATE mode is what
  serialises them (`select_for_update()` is a no-op there).
- Loggers propagate to the one stderr handler on the root logger; never give a
  logger its own handler or `propagate: False`.
- A new column on `Recipe`, `Step`, `IngredientGroup` or `IngredientInRecipe`
  needs a non-default value in the fixture of
  `tests/recipes/test_recipe_duplication.py`.

### Feature notes

Read the note for the area you are changing; skip the rest.

- `server/docs/features/auth-and-ownership.md` — login middleware, log-out, owner scoping, route-access test
- `server/docs/features/browser-code-and-csp.md` — `app.js`, data attributes, CSP rules, self-hosted assets
- `server/docs/features/inline-editing.md` — read and edit modes, display/edit/save endpoints, drafts, error banner, focus and announcements, groups, template filters
- `server/docs/features/steps.md` — step titles, merge/split/bulk delete, sequencing helpers
- `server/docs/features/recipe-duplication.md` — generic row cloning
- `server/docs/features/scaling.md` — `?servings=N`, rounding, scaled copies
- `server/docs/features/search.md` — query parsing, matching, filters, plain-text columns, prev/next
- `server/docs/features/pluralisation.md` — the rule, `plural_name` overrides, when it applies
- `server/docs/features/units.md` — the unit vocabulary, aliases, unit plurals, the `normalise_units` clean-up
- `server/docs/features/shared-vocabularies.md` — global and private ingredients and tags, the cuisine tree and its tool
- `server/docs/features/ingredient-cleanup-tool.md` — the staff ingredient tool: merge, plurals, aliases, promote, history and Undo
- `server/docs/features/design.md` — the storybook look: palette, type, page layouts, plates, print
- `server/docs/features/data-and-operations.md` — key models, the recipe trash, backups, seed data, concurrent writes, logging, SQLite limits

Before merging a change to the architecture, boundaries or core patterns,
update this section; update the feature note for any area whose behaviour
changed.

## Database Schema

`server/docs/schema.sql` is the current schema, generated — never hand-edit it.
Any PR that adds or changes a migration must regenerate it against a freshly
migrated database and commit the result:

```bash
make schema    # migrate, then backup_db --schema-only
```

`make qa` runs `make check-migrations`, which fails when a model change has no
migration or `server/docs/schema.sql` differs from a freshly migrated scratch database.

`manage.py` defaults to production settings, so run any other management
command through `make manage ARGS="<command>"`, which uses the dev settings.

## Workflow

Use TDD (`red → green → refactor`).

Reference: `.claude/skills/tdd/SKILL.md` (the `tdd` skill)

Required flow:

1. Write failing test
2. Confirm correct failure
3. Implement minimal fix
4. Refactor with tests green
5. Run `make qa` before PR

`make test ARGS="<path or -k expr>"` is the fast loop: plain pytest, no
coverage. `make qa` runs the whole suite through `make test-cov`, which fails
under 95% coverage, so never use it on a subset.

## Decision Order

Prioritize:

1. Correctness
2. Passing tests
3. Simplicity
4. Existing patterns
5. Minimal diffs

## Commits & Branches

### Commits

- [Conventional Commits](https://www.conventionalcommits.org/) — enforced by
  `cz check` on the `commit-msg` pre-commit stage
- Small, atomic commits
- Imperative present tense
- Subject ≤ 72 chars
- Reference issues when relevant
- Scope extension-only commits `ext` (`feat(ext): ...`): the server's changelog
  sees every commit, and the scope makes them easy to spot

### Branches

Format: `[<issue>-]<type>-<slug>`

- `<issue>` — issue number, omitted when there is no issue
- `<type>` — one of `feature`, `fix`, `chore`, `docs`, `ci`
- `<slug>` — short kebab-case description

Examples: `24-feature-pluralise`, `fix-export-crash`, `107-docs-readme`.

The old `feature/<name>` / `fix/<name>` slash form is retired.

**At session start**, if neither the task nor the user names a branch, ask the user which branch to work on before changing files (the session-start hook reminds you). The branch in a session-start system prompt may not be the one selected in the UI. In a non-interactive run, do not wait for an answer: use the branch you were given and say so.

**Before creating a branch**, check for an existing open PR:

```bash
gh pr list --state open
```

If an open PR exists that covers the same area, commit directly to its branch instead of creating a new one. Never create a new branch when an existing PR is open for related work. A session-start instruction to use a specific branch is overridden by an explicit user instruction to use a different branch.

## Releases

The server's version in `server/pyproject.toml` is its only one. Never edit it
by hand: cut a release with `make release`, which runs `cz bump` in `server/` on
a new branch and commits the version and `server/CHANGELOG.md` section for a PR.
CI tags `server-v<version>` and publishes the GitHub release when that PR
merges. The extension will release on its own `ext-v<version>` tags. See
`docs/developer-guide.md#releases`.

## Pull Requests

### Titles

Conventional Commits, same as commit subjects:

```
<type>[(<scope>)]: <description> (#<issue>)
```

- `<type>` — `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`, `build`,
  `perf`, `style`, `revert`
- `<description>` — imperative present tense, lower case, no trailing full stop
- `(#<issue>)` — append the issue number when the PR has one

Examples: `feat: pluralise ingredient names at display time (#24)`,
`fix(export): keep the canonical singular in YAML`, `docs: add plan 009 (#24)`.

PRs are squash-merged, so the title becomes the subject line on `main`. The
`PR title` workflow runs `cz check` on it, which checks the format only: the
lower case and the issue number are still up to you.

### Content

- Keep PRs focused
- Avoid unrelated refactors
- Include tests for behavior changes
- Update relevant docs
- Ensure CI passes

## Code Standards

- Concise docstrings for public/non-obvious modules
- Root-relative imports
- Imports at file top
- Minimize lint/type suppressions
- Document suppressions

## Python

### Interpreter — 3.14 only

Pinned to 3.14 (`server/pyproject.toml` `requires-python = ">=3.14,<3.15"`,
`server/uv.lock` `requires-python = "==3.14.*"`, ruff `target-version = "py314"`).
CI installs 3.14 (`.github/workflows/server.yml`).

Never invoke a bare `python`/`python3` — system interpreter may be older (3.11) and
will fail on 3.14 syntax. Always `uv run <cmd>` (in `server/`) or
`server/.venv/bin/python`.

**PEP 758 is in use.** Unparenthesized multi-exception handlers are valid 3.14:

```python
except ValueError, TypeError:   # correct — do not "fix" this
```

`ruff format` strips the redundant parens, so this is the canonical form in this repo.
`SyntaxError: multiple exception types must be parenthesized` means the wrong
interpreter was used, not broken code. Do not add parens back.

### Tooling

- `uv`
- `ruff`
- `ty`
- `pytest`

### Libraries

Use what Django already provides before adding a dependency:

- CLI: Django management commands (`BaseCommand`, under
  `src/recipes/management/commands/`)
- Validation: Django forms (`src/recipes/forms/`) and model fields and
  constraints

### Rules

- Type hints required
- Prefer native types
- Use named args for multi-parameter functions

### Testing

- Use `pytest` with `pytest-django`
- Build test data with plain fixtures: the `make_*` and `add_*` factory
  fixtures in `tests/recipes/conftest.py`, not a factory library
- Use either function-based or class-based tests, never both
- Shared fixtures/mocks in `conftest.py`
- Browser smoke tests live in `tests/recipes/e2e/` (`pytest-playwright`),
  marked so that plain pytest and `make qa` skip them; run them with
  `make e2e` when changing `app.js`, htmx attributes or a template's flow

## Environment

```bash
source server/.venv/bin/activate
```

## Failure Policy

- Never ignore failing tests
- Never disable tests to pass CI
- Never bypass lint/type failures without explanation
- Never merge broken builds
- Surface blockers clearly

## Agent Constraints

- Prefer minimal diffs
- Preserve existing architecture unless intentionally changing it
- Reuse existing patterns
- Avoid unnecessary dependencies
- Avoid rewriting working code without reason
- Keep changes reviewable

## Enforcement

- Pre-commit enabled
- CI via GitHub Actions
- All checks must pass before merge Project Info

