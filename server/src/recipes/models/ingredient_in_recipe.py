from django.db import models

from .ingredient import Ingredient
from .ingredient_group import IngredientGroup
from .unit import UNIT_NAME_MAX_LENGTH, Unit


class IngredientInRecipe(models.Model):
    id = models.AutoField(primary_key=True)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="+")
    substitute = models.ForeignKey(
        Ingredient, on_delete=models.PROTECT, related_name="+", blank=True, null=True
    )
    unit = models.ForeignKey(
        Unit, on_delete=models.PROTECT, related_name="+", blank=True, null=True
    )
    # Free text typed before the unit vocabulary (#67), shown as stored until
    # `normalise_units` (or an edit) moves it onto `unit`; "" once it has.
    legacy_unit = models.CharField(
        "unit as typed before #67", max_length=UNIT_NAME_MAX_LENGTH, blank=True, default=""
    )
    preparation = models.CharField("chopped, blanched...", max_length=128, blank=True, default="")
    quantity = models.DecimalField(
        "quantity as recorded in source", decimal_places=2, max_digits=7, blank=True, null=True
    )
    ingredient_group = models.ForeignKey(
        IngredientGroup, on_delete=models.CASCADE, related_name="items"
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

    class Meta:
        ordering = ["index_in_sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["ingredient_group", "index_in_sequence"],
                name="unique_ingredient_in_group",
            )
        ]

    def __str__(self) -> str:
        """Return a readable label."""
        return str(self.ingredient)
