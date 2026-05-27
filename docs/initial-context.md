# Initial Context

## Overview

Nutrisho is a Django recipe manager prototype. Stores recipes, ingredients, cuisines, and tags. Supports bulk YAML import and export.

## Tech Stack

- **Runtime**: Python 3.14
- **Framework**: Django 6.0
- **Frontend**: HTMX 2.x (via django-htmx) — inline partial swaps, no full-page reloads
- **DB**: SQLite (dev)
- **Deps**: uv
- **Lint**: ruff
- **Types**: ty
- **Tasks**: Taskfile
- **Tests**: pytest + pytest-django

## Prerequisites

- `uv` — dependency manager and task runner for Python
- `task` — Taskfile runner (`brew install go-task` / `go install github.com/go-task/task/v3/cmd/task@latest`)
- `jq` — required by `.claude/hooks/` for JSON parsing (`brew install jq` / `apt install jq`)

## Project Layout

```
src/
  nutrisho/      # Django project (settings, urls, wsgi)
  recipes/       # Main app: models, views, templates, management commands
    templatetags/  # Custom template filters (recipe_filters.py)
docs/
  initial-context.md   # this file
  plans/               # active work plans
  archive/             # completed plans
tests/
  conftest.py
  recipes/             # recipe app tests
```

## Architecture

Single Django app (`recipes`) under `src/` layout. No API layer. Frontend is server-rendered Django templates with HTMX inline editing. Debug toolbar enabled in dev.

### Inline Editing Pattern

Each editable entity (field, step, ingredient, group) has three endpoints:
- `GET /<entity>/` — read-only partial (`_*_display.html`)
- `GET /<entity>/edit/` — edit widget partial (`_*_edit.html`)
- `POST /<entity>/save/` — validates and saves; returns display partial on success, edit partial with errors on failure

HTMX swaps partials in place (`hx-swap="outerHTML"`). The `+ Add` buttons (`hx-post`, `hx-swap="beforeend"`) only render a blank edit form — no row is created until its Save posts to the entity's `POST /<entity>/create/` endpoint and validation passes. The draft form submits its DOM `position` (computed at submit via `hx-on::config-request`) and the server inserts at that position (resolved against the ordered sibling list — importer-seeded sequences may be 1-based or gapped), shifting later rows, so saving multiple drafts out of order cannot diverge from the on-screen order; Cancel on an unsaved form just removes it from the DOM, so canceled adds leave no orphan rows. `Delete` buttons use `hx-post` with `hx-swap="outerHTML"`. CSRF token is injected globally via `hx-headers` on `<body>`. HTMX library is served from `django_htmx` static files (`htmx.min.js`).

Ingredient name edit uses an HTML5 `<datalist>` for autosuggest (all existing ingredient names). On save, `ingredient_name` is resolved via get-or-create so renaming creates a new `Ingredient` rather than mutating a shared one.

### Sequencing (`recipes/utils/sequencing.py`)

All `index_in_sequence` mutations go through shared, transactional helpers:
`insert_at_index` (create at a DOM position), `remove_and_compact`
(delete + close the gap), `move_in_sequence` (swap with a neighbour via a
`-1` sentinel for SQLite's per-statement unique checks). Entity views must
not reimplement index arithmetic.

Empty text fields (`short_description`, `group_name`, `unit`,
`preparation`) are stored as `""`, never `NULL`; YAML export serializes
them as `null` and import coerces `null` back to `""`.

### Template Filters (`recipes/templatetags/recipe_filters.py`)

- `safe_step_html` — sanitizes step text, allowing only `<b>`, `<i>`, `<s>`, `<u>` inline tags; escapes everything else. Applied in `_step_display.html`.
- `format_quantity` — strips trailing decimal zeros from `DecimalField` values (e.g. `2.50 → 2.5`, `4.00 → 4`). Applied in `_ingredient_display.html`.

### Key Models

- `Recipe` — core entity, owns name, description, cuisine, source, owner, servings (author's intended serving count; `null` when unknown)
- `Ingredient`, `IngredientGroup`, `IngredientInRecipe` — ingredient hierarchy; `IngredientInRecipe.quantity` is stored as-is from source data (not normalized to per-serving)
- `Step` — ordered recipe steps
- `Cuisine`, `Source`, `Tag` — lookup/classification models

### Data Flow

YAML files → `batch_load_yaml_recipes` management command → Django ORM → SQLite (always inserts; `id` field in YAML ignored)

Django ORM → `export_recipes_to_yaml` management command → YAML files

`delete_recipe --id <N>` removes recipes by primary key for post-import cleanup


## Constraints

- Prototype quality: no production settings, no secrets management
- SQLite only; no migrations for external DBs
- No REST API yet
- Auth uses Django's built-in User model

## Boundaries

- `src/nutrisho/` — project config only, no business logic
- `src/recipes/` — all domain logic
- Management commands in `src/recipes/management/`

## Dev Workflow

```bash
source .venv/bin/activate
task qa          # lint + typecheck + test
```

See AGENTS.md for full TDD workflow.
