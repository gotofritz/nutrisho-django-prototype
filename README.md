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

A step can carry a **title** — the heading some recipes put in front of the
instruction, like `RAGÚ` or `FOR THE STOCK`. It is optional: leave it empty and
the step reads exactly as before. Recipes imported with the heading buried in
the text (`<u>RAGÚ</u>: Sauté the beef`) were split out in one pass, so the
heading is now its own field, no longer shouted, and exports carry it
separately.

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

- **Edit** — rename them, set their family and dietary constraint, or give them a
  plural. Editing one ingredient, Save closes the panel and returns you to the
  columns; editing several, each panel saves on its own and the rest stay open,
  so **Done** is how you leave.
- **Delete** — remove them. If recipes still use one you have to pick a
  replacement, and every mention moves across, including "or use this instead"
  substitutes.
- **Merge** — choose the name to keep; the others fold into it and their recipes
  follow. Renaming the survivor afterwards is a separate Edit.
- **Merge plural** — for exactly two rows that are the same ingredient written
  singular and plural, `apple` and `apples`. Say which one is the singular (the
  likely one is already picked) and it survives, the other one's recipes follow,
  and **the other one's spelling becomes its plural**. Nothing is lost: the name
  that leaves column 2 is the one the recipe page writes above a quantity of 1.
  Plain Merge would drop it and leave the plural to be guessed from the name,
  which is wrong for anything the rule does not cover.

Typing in the search box filters the list; the counts above each column tell you
how many ingredients matched and how many you have selected.

The checkbox in the ingredient column's header selects or clears everything
currently listed — what the search box and the filter below leave, not the whole
table. It shows a tick when all of them are selected, a dash when only some are.

**Unused only** narrows the list to orphans — ingredients no recipe mentions at
all. They pile up on their own: renaming an ingredient on a recipe leaves the old
spelling behind, as does removing the last recipe that used one, and imports add
their own. Tick the filter, select the lot, Delete.

**Plural pairs only** narrows the list to ingredients stored twice, once
singular and once plural — `onion` alongside `onions`. The plural row is always
the one to lose: see *Plurals* below. Tick the filter, select a pair, **Merge
plural**.

British spelling is the canonical one, and ingredient names must now be unique
ignoring case — `Onion` and `onion` can no longer both exist. If your database
predates that rule, list the clashes **before** migrating:

```bash
python manage.py find_ingredient_duplicates
```

Merge whatever it reports with the tool above, then run the migration. The same
command also lists any singular/plural pairs it finds.

---

## Plurals

A plural is not a different ingredient — it is how one ingredient reads at a
quantity other than 1. Recipes store `onion` once and the page writes **1
onion** or **2 onions** as the quantity requires. Doubling a recipe therefore
reads correctly without anything being stored twice.

This only happens when there is no unit: `2 onions`, but `200 g onion`, never
`200 g onions`. A quantity you have not filled in stays singular.

The plural is worked out from the name — `tomato` → `tomatoes`, `leaf` →
`leaves`, `chilli` → `chillies`. English being what it is, the rule misses some:
give the ingredient a **plural** of its own in the Edit panel to fix one
(`avocado` → `avocados`). Setting the plural to the singular is how you stop a
word inflecting at all, for a `broccoli` or a `fish`. **Merge plural** fills the
same field in for you, from the row it merges away.

Nothing about this is stored on the recipe or written to YAML: exports always
carry the singular.

---

## License

[0BSD](LICENSE.md) — do whatever you like with it.

---

_Developer? See the [Developer Guide](docs/developer-guide.md)._
