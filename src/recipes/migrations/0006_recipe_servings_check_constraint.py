"""Add check constraint: Recipe.servings must be >= 1 or NULL."""

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0004_recipe_yaml_filename"),
    ]

    operations = [
        migrations.AlterField(
            model_name="recipe",
            name="servings",
            field=models.PositiveSmallIntegerField(
                blank=True,
                default=None,
                null=True,
                validators=[MinValueValidator(1)],
            ),
        ),
        migrations.AddConstraint(
            model_name="recipe",
            constraint=models.CheckConstraint(
                condition=models.Q(servings__isnull=True) | models.Q(servings__gte=1),
                name="recipes_recipe_servings_gte1_or_null",
            ),
        ),
    ]
