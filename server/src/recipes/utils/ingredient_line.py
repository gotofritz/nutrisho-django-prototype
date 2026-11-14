"""Read one free-text ingredient line, as a recipe site prints it (#78).

`1 1/2 cups flour, sifted` is a quantity, a unit, a name and a preparation.
Scraped recipes (schema.org `recipeIngredient`) hold nothing more structured
than such lines. Which words are units is the caller's vocabulary, passed in as
`is_unit`, so this stays free of Django like the other utils.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from recipes.utils.plain_text import plain_text
from recipes.utils.unit_words import append_text, not_a_unit

NAME_MAX_LENGTH = 128  # Ingredient.ingredient_name
_QUANTITY_LIMIT = Decimal(100000)  # IngredientInRecipe.quantity: 7 digits, 2 decimals
_CENT = Decimal("0.01")

_VULGAR_FRACTIONS = {
    "½": "1/2",
    "⅓": "1/3",
    "⅔": "2/3",
    "¼": "1/4",
    "¾": "3/4",
    "⅕": "1/5",
    "⅖": "2/5",
    "⅗": "3/5",
    "⅘": "4/5",
    "⅙": "1/6",
    "⅚": "5/6",
    "⅛": "1/8",
    "⅜": "3/8",
    "⅝": "5/8",
    "⅞": "7/8",
}
_AMOUNT = r"\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?"
_QUANTITY = re.compile(
    rf"^(?P<low>{_AMOUNT})(?:\s*(?:-|\u2013|\u2014|\bto\b)\s*(?P<high>{_AMOUNT}))?(?![\d/.,])\s*"
)
_BRACKETS = re.compile(r"\s*\(([^)]*)\)")


@dataclass(frozen=True)
class ParsedLine:
    """The parts of one ingredient line; the unit is as written, not yet resolved."""

    name: str
    quantity: Decimal | None = None
    unit: str = ""
    preparation: str = ""
    note: str = ""


def parse_ingredient_line(line: str, *, is_unit: Callable[[str], bool]) -> ParsedLine:
    """Split `line` into a quantity, a unit `is_unit` knows, a name, a preparation and a note.

    A unit is looked for only after a quantity, so `can of beans` stays a name.
    Text after the first comma is the preparation, text in brackets a note; a
    size (`large`) moves to the preparation and an amount phrase (`to taste`) to
    the note, as the editor asks of typed rows. A range (`1-2`) keeps its low
    end and is noted as written. A line that is only a quantity and a unit stays
    whole as the name.
    """
    text = plain_text(line)
    for char, fraction in _VULGAR_FRACTIONS.items():
        text = text.replace(char, f" {fraction}")
    text = " ".join(text.split())
    if not text:
        return ParsedLine(name="")
    notes: list[str] = []
    quantity: Decimal | None = None
    unit = ""
    rest = text
    match = _QUANTITY.match(text)
    if match is not None:
        rest = text[match.end() :]
        quantity = _amount(match["low"])
        if match["high"] is not None:
            notes.append(match.group(0).strip())
        elif quantity is None:
            notes.append(match["low"])
        unit, rest = _take_unit(rest, is_unit=is_unit)
    notes.extend(note.strip() for note in _BRACKETS.findall(rest))
    rest = _BRACKETS.sub("", rest)
    name, _, preparation = (part.strip() for part in rest.partition(","))
    name, phrase = _split_note_phrase(name)
    if not_a_unit(preparation) == "note":
        phrase, preparation = phrase or preparation, ""
    if phrase:
        notes.append(phrase)
    name, preparation = _split_size(name, preparation)
    if not name:
        return ParsedLine(name=text[:NAME_MAX_LENGTH])
    return ParsedLine(
        name=name[:NAME_MAX_LENGTH],
        quantity=quantity,
        unit=unit,
        preparation=preparation,
        note="; ".join(note for note in notes if note),
    )


def _amount(text: str) -> Decimal | None:
    """`1`, `1.5`, `1,5`, `1/2` or `1 1/2` as a two-decimal quantity, or None if too large."""
    whole, _, fraction = text.rpartition(" ")
    try:
        value = Fraction(int(whole or 0)) + (
            Fraction(fraction) if "/" in fraction else Fraction(Decimal(fraction.replace(",", ".")))
        )
    except ZeroDivisionError:
        return None
    quantity = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
        _CENT, rounding=ROUND_HALF_UP
    )
    return quantity if quantity < _QUANTITY_LIMIT else None


def _take_unit(rest: str, *, is_unit: Callable[[str], bool]) -> tuple[str, str]:
    """The unit `rest` starts with, two words or one, and what follows it, minus an `of`."""
    words = rest.split()
    for count in (2, 1):
        if len(words) < count:
            continue
        candidate = " ".join(words[:count]).removesuffix(".")
        if is_unit(candidate):
            words = words[count:]
            if words and words[0].lower() == "of":
                words = words[1:]
            return candidate, " ".join(words)
    return "", rest


def _split_note_phrase(name: str) -> tuple[str, str]:
    """`name` without a trailing amount phrase (`salt to taste`), and the phrase."""
    words = name.split()
    for count in (2, 1):
        if len(words) > count and not_a_unit(" ".join(words[-count:])) == "note":
            return " ".join(words[:-count]), " ".join(words[-count:])
    return name, ""


def _split_size(name: str, preparation: str) -> tuple[str, str]:
    """`name` without a leading size (`large eggs`), and the preparation led by it."""
    words = name.split()
    for count in (2, 1):
        if len(words) > count and not_a_unit(" ".join(words[:count])) == "preparation":
            size = " ".join(words[:count])
            return " ".join(words[count:]), append_text(preparation, size)
    return name, preparation
