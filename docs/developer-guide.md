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

## Populating the database

```bash
uv run poe filldb
```

Wipes the DB, runs migrations, creates the initial user, and imports all YAML recipes from `recipes_yaml/`.

To import a single folder:

```bash
source .venv/bin/activate
python manage.py batch_load_yaml_recipes path/to/recipes/
```

`batch_load_yaml_recipes` always inserts — it never updates or reconciles existing recipes. Any `id` field in the YAML is ignored. Shared entities (Cuisine, Ingredient, Tag) are reused via `get_or_create`.

To delete recipes by ID:

```bash
python manage.py delete_recipe --id 42
python manage.py delete_recipe --id 42 43 44
```

## Exporting recipes

```bash
uv run poe export                     # export all to recipes_yaml/
uv run poe export --missing-only   # skip existing files
uv run poe export --id 42          # single recipe
```

Or directly:

```bash
python manage.py export_recipes_to_yaml recipes_yaml/
```

Typical workflow for fixing a recipe: export → edit YAML → delete old record (`delete_recipe --id <N>`) → re-import with `batch_load_yaml_recipes`.

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
