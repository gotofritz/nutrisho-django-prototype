# Plan 003: YAML Export and Servings

## Status: Draft

## Context

~340 recipes loaded from YAML into DB. Some recipes exist only in DB (no YAML file). All YAML files show `serves: 1` — quantities were pre-normalised during XML→YAML conversion — but not all are accurate. The loader (`batch_load_yaml_recipes.py:74`) reads `serves` but discards it. Template hardcodes "Serves 4". Manual cleanup of servings data is needed.

**Target data contract:**
- `IngredientInRecipe.quantity` = amount for one serving
- `Recipe.servings` = author's intended serving count
- Display: `display_quantity = quantity * recipe.servings`

**Cleanup workflow:** export → manually fix `serves`/quantities → re-import.

## Step 0: YAML export command

### 0.1 Management command: `export_recipes_to_yaml`

Add `src/recipes/management/commands/export_recipes_to_yaml.py`. Inverse of `batch_load_yaml_recipes` — reads DB, writes YAML files.

Usage:
```bash
python manage.py export_recipes_to_yaml recipes_yaml/            # all recipes
python manage.py export_recipes_to_yaml recipes_yaml/ --id 42   # single recipe
python manage.py export_recipes_to_yaml recipes_yaml/ --missing-only  # DB-only recipes
```

Output format must match existing YAML schema exactly for clean round-trips.
Each file named `{recipe_name}.yml`.

TDD cycles:
1. Test: command with empty DB writes no files
2. Test: single recipe with one group/ingredient produces expected YAML structure
3. Test: `--id` flag exports only that recipe
4. Test: `--missing-only` skips recipes that already have a YAML file on disk
5. Test: recipe name with special characters produces safe filename
6. Test: round-trip (export then re-import) produces identical DB state

Files changed:
- `src/recipes/management/commands/export_recipes_to_yaml.py` (new)
- `tests/recipes/test_export_recipes.py` (new)
- `tests/recipes/conftest.py` — add recipe/ingredient fixtures

### 0.2 Taskfile shortcut

Add `task export` to `Taskfile.yml` with sensible defaults.

Files changed:
- `Taskfile.yml`

---

## Step 1: Add `servings` to data model

### 1.1 Migration: add `servings` field to `Recipe`

Add `servings = models.PositiveSmallIntegerField(default=1)` to `Recipe`.
Default 1 is safe — many records have inaccurate serving data pending manual cleanup.

TDD cycles:
1. Test: new Recipe has `servings=1` by default
2. Test: Recipe can be created with explicit servings value

Files changed:
- `src/recipes/models/recipe.py` — add field
- `tests/recipes/test_recipe_model.py` (new)
- New migration

### 1.2 Update YAML loader

In `batch_load_yaml_recipes.py`:
- Stop discarding `serves` (line 74 currently assigns to `_`)
- Switch from `get_or_create` to `update_or_create` for Recipe, IngredientInRecipe, Step
- Add `--dry-run` flag: report changes without writing to DB
- Pass `servings=serves` to Recipe upsert

TDD cycles:
1. Test: loading YAML with `serves: 4` creates Recipe with `servings=4`
2. Test: loading YAML with `serves: 1` creates Recipe with `servings=1`
3. Test: YAML missing `serves` key defaults to 1
4. Test: re-importing YAML with changed `serves` updates existing Recipe
5. Test: re-importing YAML with changed quantity updates existing ingredient
6. Test: `--dry-run` reports changes without modifying DB

Files changed:
- `src/recipes/management/commands/batch_load_yaml_recipes.py`
- `tests/recipes/test_batch_load.py` (new)

### 1.3 Clarify data contract in docstrings

Document the quantity/servings contract in model docstrings.
Note that accuracy depends on manual cleanup being complete.

Files changed:
- `src/recipes/models/recipe.py` — add docstring
- `src/recipes/models/ingredient_in_recipe.py` — add docstring to `quantity`

### 1.4 Template: replace hardcoded "Serves 4"

Replace `<h3 class="serves">Serves 4</h3>` with
`<h3 class="serves">Serves {{ recipe.servings }}</h3>`.

Files changed:
- `src/recipes/templates/recipes/recipe.html`

### 1.5 Display scaled quantities

Custom template filter `scale` for displaying `quantity × servings`.

TDD cycles:
1. Test: `scale` filter with quantity=2.5 and servings=4 returns 10.0
2. Test: `scale` filter with None quantity returns empty string
3. Test: `scale` filter with servings=1 returns original quantity
4. Test: recipe detail page renders scaled quantities (Django test client)

Files changed:
- `src/recipes/templatetags/recipe_filters.py` (new)
- `tests/recipes/test_template_filters.py` (new)
- `src/recipes/templates/recipes/recipe.html`

---

## Open questions

1. **DB-only recipes**: Should exported YAML files be committed to the repo or kept separately?
2. **Data trust**: Show visual indicator (e.g. "unverified") for recipes where `servings=1` might be placeholder? Or just prioritise manual cleanup first.
