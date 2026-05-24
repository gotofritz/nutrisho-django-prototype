"""Add servings to Recipe; nullable so unknown serving counts are preserved."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0002_alter_cuisine_id_alter_ingredient_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="recipe",
            name="servings",
            field=models.PositiveSmallIntegerField(blank=True, null=True, default=None),
        ),
    ]
