"""Tests for the English pluralisation rule (plan 009, phase 1)."""

import pytest

from recipes.utils.pluralise import pluralise


@pytest.mark.parametrize(
    ("singular", "expected"),
    [
        # already plural or mass in this domain — left alone
        ("oats", "oats"),
        ("chives", "chives"),
        ("asparagus", "asparagus"),
        # sibilant endings take -es
        ("squash", "squashes"),
        ("box", "boxes"),
        # consonant + y -> ies
        ("anchovy", "anchovies"),
        ("berry", "berries"),
        ("cherry", "cherries"),
        # vowel + y keeps the y
        ("bay", "bays"),
        # consonant + o -> es
        ("tomato", "tomatoes"),
        ("potato", "potatoes"),
        # vowel + o just takes -s
        ("radio", "radios"),
        # -i -> ies
        ("chilli", "chillies"),
        # f / fe -> ves
        ("leaf", "leaves"),
        ("knife", "knives"),
        # the common case
        ("onion", "onions"),
        ("carrot", "carrots"),
        ("egg", "eggs"),
    ],
)
def test_rule_table(singular: str, expected: str):
    assert pluralise(singular) == expected


def test_only_the_last_word_is_pluralised():
    assert pluralise("spring onion") == "spring onions"
    assert pluralise("sun dried tomato") == "sun dried tomatoes"


def test_empty_string_stays_empty():
    assert pluralise("") == ""
    assert pluralise("   ") == "   "


def test_surrounding_whitespace_does_not_swallow_the_suffix():
    assert pluralise("  onion  ") == "  onions  "
