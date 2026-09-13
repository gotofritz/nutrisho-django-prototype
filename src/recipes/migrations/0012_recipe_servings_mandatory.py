"""Make Recipe.servings mandatory: NOT NULL, default 1, check constraint >= 1.

Aborts if any row still has servings=NULL rather than inventing a serving count.
Run `python scripts/check_recipe_servings.py` first to list offending recipes.
"""

from django.core.validators import MinValueValidator
from django.db import migrations, models


def _assert_no_null_servings(apps, schema_editor):
    Recipe = apps.get_model("recipes", "Recipe")
    offenders = list(
        Recipe.objects.filter(servings__isnull=True).values_list("pk", "recipe_name")[:10]
    )
    if offenders:
        listed = ", ".join(f"#{pk} {name!r}" for pk, name in offenders)
        raise RuntimeError(
            "Migration 0012 aborted: recipes without a serving count still exist "
            f"({listed}). Set servings on them (or delete them) and re-run. "
            "Use `python scripts/check_recipe_servings.py` for the full list."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0011_recipe_name_owner_unique"),
    ]

    operations = [
        migrations.RunPython(_assert_no_null_servings, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="recipe",
            name="recipes_recipe_servings_gte1_or_null",
        ),
        migrations.AlterField(
            model_name="recipe",
            name="servings",
            field=models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)]),
        ),
        migrations.AddConstraint(
            model_name="recipe",
            constraint=models.CheckConstraint(
                condition=models.Q(servings__gte=1),
                name="recipes_recipe_servings_gte1",
            ),
        ),
    ]
