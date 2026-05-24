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
python manage.py batch_load_yaml_recipes my_recipes/
```

Then open <http://127.0.0.1:8000/recipes/> in your browser.

---

## Editing recipes

Web-based editing is planned for a future release. For now, ask your developer to edit the database directly.

---

## License

[0BSD](LICENSE.md) — do whatever you like with it.

---

_Developer? See the [Developer Guide](docs/developer-guide.md)._
