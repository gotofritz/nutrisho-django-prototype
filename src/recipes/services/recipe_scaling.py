"""Save a recipe scaled to another serving count as a new recipe (#36).

The original is never touched: scaling for the page is done at display time
(`recipes/utils/scaling.py`), and a permanent scaled version is a copy made with
`duplicate_recipe` whose servings and quantities are then set from the original's
values. The copy stores quantities to two decimals, the column's precision; a
quantity that would overflow the column or round to 0 refuses the whole copy.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from recipes.models import IngredientInRecipe, Recipe
from recipes.services.recipe_duplication import duplicate_recipe
from recipes.utils.scaling import scale_factor, scale_quantity

_CENT = Decimal("0.01")
_MAX_QUANTITY = Decimal("99999.99")  # IngredientInRecipe.quantity: max_digits=7, decimal_places=2


class ScaleError(ValueError):
    """The recipe cannot be stored at the requested serving count."""

    def __init__(self, ingredient: str, *, servings: int, outcome: str) -> None:
        noun = "serving" if servings == 1 else "servings"
        super().__init__(f"{ingredient} would {outcome} at {servings} {noun}.")


def save_scaled_copy(original: Recipe, *, servings: int) -> Recipe:
    """Copy `original` at `servings` servings, with quantities scaled to match."""
    factor = scale_factor(servings=int(original.servings), target=servings)  # ty: ignore[invalid-argument-type]  # no Django stubs
    with transaction.atomic():
        copy = duplicate_recipe(original)
        copy.servings = servings  # ty: ignore[invalid-assignment]  # no Django stubs
        copy.save(update_fields=["servings"])
        if factor is None:
            return copy
        rows = list(
            IngredientInRecipe.objects.select_related("ingredient").filter(
                ingredient_group__recipe=copy, quantity__isnull=False
            )
        )
        for row in rows:
            stored = Decimal(row.quantity)
            scaled = scale_quantity(stored, factor).quantize(_CENT, rounding=ROUND_HALF_UP)
            name = row.ingredient.ingredient_name
            if scaled > _MAX_QUANTITY:
                raise ScaleError(name, servings=servings, outcome="be too large")
            if stored and not scaled:
                raise ScaleError(name, servings=servings, outcome="round to 0")
            row.quantity = scaled
        IngredientInRecipe.objects.bulk_update(rows, ["quantity"])
    return copy
