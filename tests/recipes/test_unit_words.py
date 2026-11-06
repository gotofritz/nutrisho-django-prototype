"""Tests for the words typed as units that are not units (#67)."""

import pytest

from recipes.utils.unit_words import append_text, not_a_unit


@pytest.mark.parametrize("word", ["small", "Medium", " LARGE ", "extra large", "big"])
def test_size_words_belong_in_preparation(word):
    """A size describes the ingredient, so it moves to preparation."""
    assert not_a_unit(word) == "preparation"


@pytest.mark.parametrize("word", ["to taste", "To Taste", "as needed"])
def test_amount_phrases_belong_in_the_note(word):
    """`to taste` is not a measure: it goes to the note, beside no quantity."""
    assert not_a_unit(word) == "note"


@pytest.mark.parametrize("word", ["g", "tbsp", "tbso", "", "smallish"])
def test_anything_else_is_not_classified(word):
    """Only the listed words count; a unit or a typo is someone else's job."""
    assert not_a_unit(word) is None


def test_append_text_fills_an_empty_field():
    """Nothing there yet: the word alone."""
    assert append_text("", "small") == "small"


def test_append_text_leads_with_the_word():
    """`small, chopped` reads as one preparation."""
    assert append_text("chopped", "small") == "small, chopped"


def test_append_text_does_not_repeat_a_word_already_there():
    """Running the clean-up twice, or a note that already says it, adds nothing."""
    assert append_text("small, chopped", "small") == "small, chopped"
    assert append_text("To taste", "to taste") == "To taste"
