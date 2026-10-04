from django.db import models

from .recipe import Recipe


class IngredientGroup(models.Model):
    id = models.AutoField(primary_key=True)
    group_name = models.CharField("Label for group", max_length=64, blank=True, default="")
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="ingredients_group")
    index_in_sequence = models.SmallIntegerField("Where to show this group, for a given recipe?")
    objects = models.Manager()

    class Meta:
        ordering = ["index_in_sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipe", "index_in_sequence"],
                name="unique_ingredient_group_in_recipe",
            )
        ]

    def __str__(self) -> str:
        """Return a readable label."""
        return str(self.group_name or f"Group {self.index_in_sequence}")

    def natural_key(self):
        """Return the natural key used by fixtures."""
        return self.group_name
