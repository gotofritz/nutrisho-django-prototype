"""Make cuisine names unique ignoring case.

Before #34 the editor matched cuisines case-sensitively, so `Italian` and
`italian` could both exist. Unlike ingredients (migration 0013), a cuisine is
only its name, so merging loses nothing but a spelling variant and is done here
rather than left to the owner: each group keeps its most-used spelling (ties go
to the oldest row), its recipes move to it and the other rows are deleted.
"""

import django.db.models.functions.text
from django.db import migrations, models
from django.db.models import Count
from django.db.models.functions import Lower


def merge_case_insensitive_duplicates(apps, schema_editor):
    """Fold cuisines that differ only by case into one row per name."""
    Cuisine = apps.get_model("recipes", "Cuisine")
    Recipe = apps.get_model("recipes", "Recipe")
    clashing = (
        Cuisine.objects.values(lowered=Lower("cuisine"))
        .annotate(total=Count("pk"))
        .filter(total__gt=1)
        .values_list("lowered", flat=True)
    )
    for lowered in list(clashing):
        keep, *rest = (
            Cuisine.objects.annotate(lowered=Lower("cuisine"), uses=Count("recipe"))
            .filter(lowered=lowered)
            .order_by("-uses", "pk")
        )
        Recipe.objects.filter(cuisine__in=rest).update(cuisine=keep)
        Cuisine.objects.filter(pk__in=[c.pk for c in rest]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0016_remove_recipe_yaml_filename"),
    ]

    operations = [
        migrations.RunPython(
            merge_case_insensitive_duplicates,
            migrations.RunPython.noop,
            elidable=False,
        ),
        migrations.AddConstraint(
            model_name="cuisine",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("cuisine"),
                name="cuisine_ci_unique",
            ),
        ),
    ]
