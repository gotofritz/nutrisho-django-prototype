# Initial Context

## Overview

Nutrisho is a Django recipe manager prototype. Stores recipes, ingredients, cuisines, and tags. Supports bulk YAML import.

## Tech Stack

- **Runtime**: Python 3.14
- **Framework**: Django 6.0
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
docs/
  initial-context.md   # this file
  plans/               # active work plans
  archive/             # completed plans
tests/
  conftest.py
  recipes/             # recipe app tests
```

## Architecture

Single Django app (`recipes`) under `src/` layout. No API layer yet. Frontend is server-rendered Django templates. Debug toolbar enabled in dev.

### Key Models

- `Recipe` — core entity, owns name, description, cuisine, source, owner
- `Ingredient`, `IngredientGroup`, `IngredientInRecipe` — ingredient hierarchy
- `Step` — ordered recipe steps
- `Cuisine`, `Source`, `Tag` — lookup/classification models

### Data Flow

YAML files → `batch_load_yaml_recipes` management command → Django ORM → SQLite

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
