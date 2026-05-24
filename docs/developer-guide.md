# Developer Guide

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python dependency manager
- [task](https://taskfile.dev/) — task runner (`brew install go-task`)
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
task run
```

Opens at <http://127.0.0.1:8000/recipes/>.

## Populating the database

```bash
task filldb
```

Wipes the DB, runs migrations, creates the initial user, and imports all YAML recipes from `recipes_yaml/`.

To import a single folder:

```bash
source .venv/bin/activate
python manage.py batch_load_yaml_recipes path/to/recipes/
```

## Quality checks

```bash
task qa        # lint + typecheck + tests + hook regression tests
task lint      # ruff only
task typecheck # ty only
task test      # pytest with coverage (≥95% required)
```

## CSS

Tailwind CSS v4. Source: `src/recipes/static/css/tailwind.css`. Output is a build artifact — not committed.

```bash
pnpm css         # build once (minified)
pnpm css:watch   # rebuild on change
```

Or via Taskfile:

```bash
task css
task css-watch
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
| Tasks | Taskfile |
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
- Run `task qa` before opening a PR
