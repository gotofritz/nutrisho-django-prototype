"""Make ingredient names unique ignoring case.

Databases that predate this rule can hold clashes (`Onion` and `onion`), and
adding the index on top of them fails with a bare
`IntegrityError: UNIQUE constraint failed`, which says nothing about which rows
are at fault or what to do. The pre-flight check below names them and points at
the clean-up tool instead. It never edits data: picking which spelling survives
is the owner's call, and the recipes pointing at each row have to move with it.
"""

import django.db.models.functions.text
from django.core.management.base import CommandError
from django.db import migrations, models
from django.db.models import Count
from django.db.models.functions import Lower


def reject_case_insensitive_duplicates(apps, schema_editor):
    """Abort with an actionable message if any names differ only by case."""
    Ingredient = apps.get_model("recipes", "Ingredient")
    clashing = (
        Ingredient.objects.values(lowered=Lower("ingredient_name"))
        .annotate(total=Count("pk"))
        .filter(total__gt=1)
        .order_by("lowered")
        .values_list("lowered", flat=True)
    )
    groups = [
        ", ".join(
            Ingredient.objects.filter(ingredient_name__iexact=name)
            .order_by("ingredient_name")
            .values_list("ingredient_name", flat=True)
        )
        for name in clashing
    ]
    if not groups:
        return
    listed = "\n  ".join(groups)
    raise CommandError(
        "Cannot make ingredient names unique ignoring case: these differ only by "
        f"case and have to be merged first.\n\n  {listed}\n\n"
        "Run `manage.py find_ingredient_duplicates` to list them again, merge each "
        "group at /recipes/ingredients/manage/ (the app runs fine without this "
        "migration), then re-run migrate."
    )


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0012_recipe_servings_mandatory"),
    ]

    operations = [
        migrations.RunPython(
            reject_case_insensitive_duplicates,
            migrations.RunPython.noop,
            elidable=False,
        ),
        migrations.AddConstraint(
            model_name="ingredient",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("ingredient_name"),
                name="ingredient_name_ci_unique",
            ),
        ),
    ]
