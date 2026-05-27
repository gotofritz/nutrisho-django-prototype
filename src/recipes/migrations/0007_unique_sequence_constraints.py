"""Add unique constraints on IngredientGroup and IngredientInRecipe sequence indexes."""

from django.db import migrations, models


def _check_no_duplicate_indices(apps, schema_editor):
    """Abort migration if duplicate sequence indexes already exist in the database.

    Raises RuntimeError with a remediation message so the operator knows which
    rows to fix before re-running the migration.
    """
    IngredientGroup = apps.get_model("recipes", "IngredientGroup")
    IngredientInRecipe = apps.get_model("recipes", "IngredientInRecipe")

    seen_groups: set[tuple] = set()
    for grp in IngredientGroup.objects.all():
        key = (grp.recipe_id, grp.index_in_sequence)
        if key in seen_groups:
            raise RuntimeError(
                f"Cannot apply migration: duplicate IngredientGroup rows found with "
                f"(recipe_id={grp.recipe_id}, index_in_sequence={grp.index_in_sequence}). "
                f"Deduplicate these rows in the database before running this migration."
            )
        seen_groups.add(key)

    seen_iir: set[tuple] = set()
    for iir in IngredientInRecipe.objects.all():
        key = (iir.ingredient_group_id, iir.index_in_sequence)
        if key in seen_iir:
            raise RuntimeError(
                f"Cannot apply migration: duplicate IngredientInRecipe rows found with "
                f"(ingredient_group_id={iir.ingredient_group_id}, index_in_sequence={iir.index_in_sequence}). "
                f"Deduplicate these rows in the database before running this migration."
            )
        seen_iir.add(key)


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0006_recipe_servings_check_constraint"),
    ]

    operations = [
        migrations.RunPython(_check_no_duplicate_indices, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="ingredientgroup",
            constraint=models.UniqueConstraint(
                fields=["recipe", "index_in_sequence"],
                name="unique_ingredient_group_in_recipe",
            ),
        ),
        migrations.AddConstraint(
            model_name="ingredientinrecipe",
            constraint=models.UniqueConstraint(
                fields=["ingredient_group", "index_in_sequence"],
                name="unique_ingredient_in_group",
            ),
        ),
    ]
