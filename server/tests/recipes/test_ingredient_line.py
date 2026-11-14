"""Tests for reading one free-text ingredient line (#78)."""

from decimal import Decimal

import pytest

from recipes.utils.ingredient_line import ParsedLine, parse_ingredient_line

_UNITS = {"g", "kg", "cup", "cups", "tbsp", "tsp", "fl oz", "clove", "cloves", "can", "ml"}


def _parse(line: str) -> ParsedLine:
    return parse_ingredient_line(line, is_unit=lambda text: text.lower() in _UNITS)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("2 onions", ParsedLine(name="onions", quantity=Decimal(2))),
        ("200 g flour", ParsedLine(name="flour", quantity=Decimal(200), unit="g")),
        # a unit run into its number
        ("200g flour", ParsedLine(name="flour", quantity=Decimal(200), unit="g")),
        ("1.5 kg potatoes", ParsedLine(name="potatoes", quantity=Decimal("1.5"), unit="kg")),
        # a decimal comma
        ("1,5 kg potatoes", ParsedLine(name="potatoes", quantity=Decimal("1.5"), unit="kg")),
        ("1/2 tsp salt", ParsedLine(name="salt", quantity=Decimal("0.5"), unit="tsp")),
        ("1 1/2 cups milk", ParsedLine(name="milk", quantity=Decimal("1.5"), unit="cups")),
        ("½ tsp salt", ParsedLine(name="salt", quantity=Decimal("0.5"), unit="tsp")),
        ("1½ cups milk", ParsedLine(name="milk", quantity=Decimal("1.5"), unit="cups")),
        # thirds are rounded to the two decimals a quantity holds
        ("1/3 cup sugar", ParsedLine(name="sugar", quantity=Decimal("0.33"), unit="cup")),
        # two-word units, and `of` after a unit
        ("2 fl oz of cream", ParsedLine(name="cream", quantity=Decimal(2), unit="fl oz")),
        # a trailing full stop on the unit
        ("1 tbsp. oil", ParsedLine(name="oil", quantity=Decimal(1), unit="tbsp")),
        # after the first comma comes the preparation
        (
            "3 cloves garlic, finely chopped",
            ParsedLine(
                name="garlic", quantity=Decimal(3), unit="cloves", preparation="finely chopped"
            ),
        ),
        # brackets are a note
        (
            "200 g (7 oz) butter, softened",
            ParsedLine(
                name="butter", quantity=Decimal(200), unit="g", preparation="softened", note="7 oz"
            ),
        ),
        # a size describes the ingredient
        (
            "2 large eggs",
            ParsedLine(name="eggs", quantity=Decimal(2), preparation="large"),
        ),
        # an amount phrase is a note
        ("salt, to taste", ParsedLine(name="salt", note="to taste")),
        ("Salt to taste", ParsedLine(name="Salt", note="to taste")),
        # a range keeps its low end, and says so in the note
        (
            "1-2 cloves garlic",
            ParsedLine(name="garlic", quantity=Decimal(1), unit="cloves", note="1-2"),
        ),
        (
            "2\N{EN DASH}3 tbsp oil",
            ParsedLine(name="oil", quantity=Decimal(2), unit="tbsp", note="2\N{EN DASH}3"),
        ),
        # no quantity, no unit: a word that happens to be a unit is the name
        ("can of beans", ParsedLine(name="can of beans")),
        # markup and entities from a web page
        ("<b>2</b> onions &amp; leeks", ParsedLine(name="onions & leeks", quantity=Decimal(2))),
        # a quantity and unit with nothing after them keep the line as the name
        ("2 cups", ParsedLine(name="2 cups", quantity=None)),
    ],
)
def test_parse_ingredient_line(line: str, expected: ParsedLine):
    """Quantity, unit, name, preparation and note come out of one line."""
    assert _parse(line) == expected


def test_quantity_too_large_for_the_column_stays_in_the_note():
    """A number the column cannot hold is not a quantity; the note keeps it."""
    assert _parse("1000000 g flour") == ParsedLine(name="flour", unit="g", note="1000000")


def test_long_name_is_cut_to_the_column():
    """An ingredient name is at most 128 characters."""
    assert _parse("x" * 200).name == "x" * 128


def test_blank_line():
    """A blank line has no name."""
    assert _parse("   ") == ParsedLine(name="")
