"""Input-only alternative names for a canonical ingredient (plan 008, #66)."""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from .ingredient import INGREDIENT_NAME_MAX_LENGTH, Ingredient


class IngredientAlias(models.Model):
    """`alias_name` typed or scraped means `canonical` (`eggplant` → `aubergine`).

    Aliases resolve at write time only: they are never `Ingredient` rows and no
    recipe references one, so storage and display always show the canonical
    British form. They are global and staff-defined (plan 011), so the canonical
    is always a global row, and a name is either an ingredient or an alias,
    never both.
    """

    id = models.AutoField(primary_key=True)
    alias_name = models.CharField(max_length=INGREDIENT_NAME_MAX_LENGTH)
    canonical = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name="aliases")
    objects = models.Manager()

    class Meta:
        verbose_name_plural = "ingredient aliases"
        constraints = [
            models.UniqueConstraint(
                Lower("alias_name"),
                name="ingredient_alias_name_ci_unique",
                violation_error_message="That name is already an alias.",
            ),
        ]

    def __str__(self) -> str:
        """`alias → canonical`."""
        return f"{self.alias_name} → {self.canonical}"

    def clean(self) -> None:
        """Strip the name; it must not be an ingredient, and the canonical must be global."""
        self.alias_name = str(self.alias_name).strip()  # ty: ignore[invalid-assignment]  # CharField descriptor
        if Ingredient.objects.filter(ingredient_name__iexact=self.alias_name).exists():
            msg = f"“{self.alias_name}” is already an ingredient — merge it instead."
            raise ValidationError({"alias_name": msg})
        canonical = Ingredient.objects.filter(pk=self.canonical_id).first()
        if canonical is not None and canonical.owner_id is not None:
            msg = "Aliases are global, so they can only point at a global ingredient."
            raise ValidationError({"canonical": msg})
