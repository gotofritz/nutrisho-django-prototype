"""Display-time recipe scaling (#36).

Scaling is presentation: the stored servings and quantities are the only copy of
a recipe, so every scaled view is computed afresh from them and nothing is written
back. The factor is kept as an exact `Fraction` (4 → 3 servings is 3/4, not
0.75…), and a quantity is multiplied before it is divided, so scaling down and back
up returns the stored value. Kept free of Django imports so it is testable on its
own.
"""

from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

MAX_SERVINGS = 32767  # Recipe.servings is a PositiveSmallIntegerField

_CENT = Decimal("0.01")


def parse_servings(raw: str | None) -> int | None:
    """`raw` as a serving count the model can hold, or None when it is not one."""
    try:
        servings = int((raw or "").strip())
    except ValueError:
        return None
    return servings if 1 <= servings <= MAX_SERVINGS else None


def scale_factor(*, servings: int, target: int | None) -> Fraction | None:
    """The exact factor taking `servings` to `target`, or None when there is nothing to scale."""
    if target is None or target == servings:
        return None
    return Fraction(target, servings)


def scale_quantity(quantity: Decimal, factor: Fraction) -> Decimal:
    """`quantity` times `factor`, unrounded."""
    return quantity * factor.numerator / factor.denominator


def round_for_display(value: Decimal) -> Decimal:
    """Two decimals, half up; below 0.01 two significant digits, so nothing shows as 0."""
    rounded = value.quantize(_CENT, rounding=ROUND_HALF_UP)
    if rounded or not value:
        return rounded
    return value.quantize(Decimal(1).scaleb(value.adjusted() - 1), rounding=ROUND_HALF_UP)
