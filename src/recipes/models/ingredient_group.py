from django.db import models

from .recipe import Recipe


class IngredientGroup(models.Model):
    id = models.AutoField(primary_key=True)
    group_name = models.CharField("Label for group", max_length=64, blank=True, null=True)
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="ingredients_group")
    index_in_sequence = models.SmallIntegerField("Where to show this group, for a given recipe?")
    objects = models.Manager()

    def natural_key(self):
        return self.group_name

    class Meta:
        ordering = ["index_in_sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipe", "index_in_sequence"],
                name="unique_ingredient_group_in_recipe",
            )
        ]
