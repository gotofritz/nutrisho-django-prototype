from django.db import models

from .ingredient import Ingredient
from .ingredient_group import IngredientGroup


class IngredientInRecipe(models.Model):
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.DO_NOTHING, related_name="+"
    )
    substitute = models.ForeignKey(
        Ingredient, on_delete=models.DO_NOTHING, related_name="+", null=True
    )
    measurement = models.CharField("the unit", max_length=32, null=True)
    preparation = models.CharField("chopped, blanched...", max_length=128, null=True)
    quantity = models.DecimalField(
        "how many", decimal_places=2, max_digits=7, null=True
    )
    ingredient_group = models.ForeignKey(
        IngredientGroup, on_delete=models.CASCADE, related_name="ingredient"
    )
    index_in_sequence = models.SmallIntegerField(
        "Where to show this ingredient, for a given group?"
    )
    note = models.CharField(
        "any extra info",
        max_length=128,
        null=True,
    )

    def natural_key(self):
        return (self.ingredient_group, self.quantity, self.measurement, self.name)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["index_in_sequence", "ingredient_group", "ingredient"],
                name="unique IngredientInRecipe step in sequence",
            )
        ]
        ordering = ["index_in_sequence"]
