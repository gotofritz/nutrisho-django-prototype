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

Removing the last ingredient from a group removes the group with it, as does
moving every ingredient out of one. A recipe's final group always stays, even
when empty — the **+ Add ingredient** button lives inside a group, so a recipe
with none would have nowhere to add to.

---

## Cleaning up ingredients

Ingredients are shared by every recipe, so the same thing can end up stored more
than once — `aubergine` and `eggplant`, `onion` and `onions`, `Onion` and `onion`.

**Manage ingredients** on the recipe list opens the tool — or **Clean up
duplicates** on the Ingredients page in Django admin, if that is where you
started. Four columns, left to right: the actions, every ingredient, the recipes
that use whichever ones you tick, and a read-only preview of whichever recipe you
click. When only one recipe matches it opens in the preview on its own; change the
selection or the search and the preview clears with it.
So you can see exactly what a clean-up would touch before committing to it.

Tick one or more ingredients, then:

- **Edit** — rename them, or set their family and dietary constraint. Editing one
  ingredient, Save closes the panel and returns you to the columns; editing
  several, each panel saves on its own and the rest stay open, so **Done** is how
  you leave.
- **Delete** — remove them. If recipes still use one you have to pick a
  replacement, and every mention moves across, including "or use this instead"
  substitutes.
- **Merge** — choose the name to keep; the others fold into it and their recipes
  follow. Renaming the survivor afterwards is a separate Edit.

Typing in the search box filters the list; the counts above each column tell you
how many ingredients matched and how many you have selected.

The checkbox in the ingredient column's header selects or clears everything
currently listed — what the search box and the filter below leave, not the whole
table. It shows a tick when all of them are selected, a dash when only some are.

**Unused only** narrows the list to orphans — ingredients no recipe mentions at
all. They pile up on their own: renaming an ingredient on a recipe leaves the old
spelling behind, as does removing the last recipe that used one, and imports add
their own. Tick the filter, select the lot, Delete.

British spelling is the canonical one, and ingredient names must now be unique
ignoring case — `Onion` and `onion` can no longer both exist. If your database
predates that rule, list the clashes **before** migrating:

```bash
python manage.py find_ingredient_duplicates
```

Merge whatever it reports with the tool above, then run the migration.

---

## License

[0BSD](LICENSE.md) — do whatever you like with it.

---

_Developer? See the [Developer Guide](docs/developer-guide.md)._
