"""Tests for the display-time scaling helpers (#36)."""

from decimal import Decimal
from fractions import Fraction

import pytest

from recipes.utils.scaling import (
    MAX_SERVINGS,
    parse_servings,
    round_for_display,
    scale_factor,
    scale_quantity,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("6", 6),
        (" 6 ", 6),
        ("1", 1),
        (str(MAX_SERVINGS), MAX_SERVINGS),
        (None, None),
        ("", None),
        ("abc", None),
        ("0", None),
        ("-2", None),
        ("1.5", None),
        (str(MAX_SERVINGS + 1), None),
    ],
)
def test_parse_servings(raw: str | None, expected: int | None):
    """Only whole serving counts the model can hold are accepted."""
    assert parse_servings(raw) == expected


def test_scale_factor_is_exact():
    """4 → 3 servings is exactly 3/4, not a rounded decimal."""
    assert scale_factor(servings=4, target=3) == Fraction(3, 4)


def test_scale_factor_is_none_when_nothing_to_scale():
    """Showing a recipe at its own serving count is not scaling it."""
    assert scale_factor(servings=4, target=4) is None
    assert scale_factor(servings=4, target=None) is None


def test_scale_quantity_multiplies_before_dividing():
    """2 at 4 servings is 3 at 6 servings."""
    assert scale_quantity(Decimal("2.00"), Fraction(6, 4)) == Decimal("3")


def test_scale_quantity_round_trips_without_drift():
    """Scaling is computed from the stored value, so dividing by 3 then multiplying by 3 is still 1."""
    down = Fraction(1, 3)
    up = Fraction(3, 1)
    assert scale_quantity(Decimal("1"), down * up) == Decimal("1")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("3"), "3"),
        (Decimal("1") / Decimal("3"), "0.33"),
        (Decimal("2") / Decimal("3"), "0.67"),
        (Decimal("0.025"), "0.03"),  # half up, not banker's rounding
        (Decimal("0.0025"), "0.0025"),  # below 0.01: two significant digits, never 0
        (Decimal("0.004"), "0.004"),
        (Decimal("0.00123"), "0.0012"),
        (Decimal("0"), "0"),
        (Decimal("200") / Decimal("2"), "100"),  # 1E+2 from the division
    ],
)
def test_round_for_display(value: Decimal, expected: str):
    """Two decimals, but a non-zero amount never displays as 0."""
    rounded = round_for_display(value)
    assert format(rounded.normalize(), "f") == expected
