# Recipe Duplication (`recipes/services/recipe_duplication.py`)

"Duplicate recipe" copies rows generically: `_clone` reads every
`_meta.concrete_fields` column except the pk and takes overrides by attname
(`recipe_id`, `ingredient_group_id`), so foreign keys are copied by id and a column
added to `Recipe`, `Step`, `IngredientGroup` or `IngredientInRecipe` is carried
over without editing the service (#35). Each level is one `bulk_create` and tags
one `add`, so a copy costs a fixed number of queries whatever the recipe's size.
Only the name allocation retries, inside its own savepoint; an IntegrityError on a
child row rolls the whole copy back. `tests/recipes/test_recipe_duplication.py`
walks every concrete field of the four models and fails if its fixture leaves one
at its default, so a new column must be added to that fixture.
