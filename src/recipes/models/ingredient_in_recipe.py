from typing import cast

from django.db import models

from .ingredient import Ingredient
from .ingredient_group import IngredientGroup


class IngredientInRecipe(models.Model):
    id = models.AutoField(primary_key=True)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="+")
    substitute = models.ForeignKey(
        Ingredient, on_delete=models.PROTECT, related_name="+", blank=True, null=True
    )
    unit = models.CharField("the unit", max_length=32, blank=True, default="")
    preparation = models.CharField("chopped, blanched...", max_length=128, blank=True, default="")
    quantity = models.DecimalField(
        "quantity as recorded in source", decimal_places=2, max_digits=7, blank=True, null=True
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
        blank=True,
    )
    objects = models.Manager()

    def natural_key(self):
        return (
            cast(IngredientGroup, self.ingredient_group).natural_key(),
            str(self.quantity) if self.quantity is not None else None,
            self.unit,
            cast(Ingredient, self.ingredient).ingredient_name,
        )

    class Meta:
        ordering = ["index_in_sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["ingredient_group", "index_in_sequence"],
                name="unique_ingredient_in_group",
            )
        ]
