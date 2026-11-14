"""Rename the reverse accessors to plurals (#79).

`recipe.step`, `recipe.tag`, `recipe.ingredients_group`, `group.ingredient`
and `Tag.recipe` become `steps`, `tags`, `ingredient_groups`, `items` and
`Tag.recipes`. The tag-recipe table keeps its name, so no SQL runs.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0027_drop_unused_source_and_step_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="step",
            name="recipe",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="steps",
                to="recipes.recipe",
            ),
        ),
        migrations.AlterField(
            model_name="ingredientgroup",
            name="recipe",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ingredient_groups",
                to="recipes.recipe",
            ),
        ),
        migrations.AlterField(
            model_name="ingredientinrecipe",
            name="ingredient_group",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="items",
                to="recipes.ingredientgroup",
            ),
        ),
        # SQLite's schema editor rebuilds an M2M table on any change to its
        # field, even with the table name pinned, so the Tag rename touches
        # Django's state only: the table already has the name and columns.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameField(model_name="tag", old_name="recipe", new_name="recipes"),
                migrations.AlterField(
                    model_name="tag",
                    name="recipes",
                    field=models.ManyToManyField(
                        blank=True,
                        db_table="recipes_tag_recipe",
                        related_name="tags",
                        to="recipes.recipe",
                    ),
                ),
            ],
        ),
    ]
