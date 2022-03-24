from django.db import models

from .recipe import Recipe


class IngredientGroup(models.Model):
    name = models.CharField("Label for group", max_length=64, null=True)
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name="ingredients_group"
    )
    index_in_sequence = models.SmallIntegerField(
        "Where to show this group, for a given recipe?"
    )

    def natural_key(self):
        return self.name

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["index_in_sequence", "recipe"],
                name="unique IngredientGroup step in sequence",
            )
        ]
        ordering = ["index_in_sequence"]
