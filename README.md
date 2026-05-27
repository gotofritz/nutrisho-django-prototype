# Nutrisho

[![CI](https://github.com/gotofritz/nutrisho-django-prototype/actions/workflows/ci.yml/badge.svg)](https://github.com/gotofritz/nutrisho-django-prototype/actions/workflows/ci.yml)
[![Coverage](https://raw.githubusercontent.com/gotofritz/nutrisho-django-prototype/badges/coverage.svg)](https://github.com/gotofritz/nutrisho-django-prototype/actions/workflows/ci.yml)
[![License: 0BSD](https://img.shields.io/badge/license-0BSD-green.svg)](LICENSE.md)

A personal recipe manager. Browse, import, and organise your recipes in one place.

---

## What it does

- Browse your recipe collection
- View ingredients, steps, and serving sizes
- Navigate between recipes

---

## Importing recipes

Recipes live in YAML files. To add a batch, drop them into a folder (e.g. `my_recipes/`) and ask your developer to run the import command.

If you have direct access to the server:

```bash
python manage.py batch_load_yaml_recipes my_recipes/ --user <username>
```

Then open <http://127.0.0.1:8000/recipes/> in your browser.

---

## Exporting recipes

To export recipes from the database back to YAML files:

```bash
python manage.py export_recipes_to_yaml recipes_yaml/ --user <username>
```

Use `--missing-only` to skip recipes that already have a file on disk, or `--id 42` to export a single recipe.

---

## Editing recipes

Inline editing is available on every recipe detail page. Click any field, step, ingredient, or group header to edit it in place. Changes save immediately without a page reload.

You can also:
- Add and delete steps
- Add ingredients to any group
- Add and delete ingredient groups

---

## License

[0BSD](LICENSE.md) — do whatever you like with it.

---

_Developer? See the [Developer Guide](docs/developer-guide.md)._
