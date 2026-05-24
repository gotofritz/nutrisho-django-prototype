# Nutrisho

A recipe manager built with Django. Small hobbyist project not expected to grow beyond a couple of dozen users.

## Setup

```bash
cp .env.example .env
# Edit .env — set SECRET_KEY to a long random string
uv sync
```

## Quick start

### Running the app

```bash
❯ task run
```

### Importing yaml recipes

Create a folder recipes_xxxx/, next to the other ones, then:

```bash
❯ source .venv/bin/activate
❯ python manage.py batch_load_yaml_recipes recipes_xxxx/
```

Then go to <http://127.0.0.1:8000/recipes/>

### Editing recipes

Edit directly in SQL, in `sql_to_edit_recipes_hack/`:

```bash
❯ sqlite3 db.sqlite3 < sql_to_edit_recipes_hack/edit_recipe.sql
```

## LICENSE

This is licensed under the [0BSD license](LICENSE.md).
