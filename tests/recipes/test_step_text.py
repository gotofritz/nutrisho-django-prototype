"""Tests for the step merge and split rules (issue #18)."""

import pytest

from recipes.utils.step_text import join_step_texts, split_step_text


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        (["Boil water", "Add salt"], "Boil water Add salt"),
        (["Boil water.", "Add salt.", "Stir."], "Boil water. Add salt. Stir."),
        # stray whitespace at the seams is not doubled up
        (["Boil water ", "  Add salt"], "Boil water Add salt"),
    ],
)
def test_join_step_texts(texts: list[str], expected: str):
    """Texts are appended in order, one space apart."""
    assert join_step_texts(texts) == expected


@pytest.mark.parametrize(
    ("text", "at", "expected"),
    [
        # cursor right after a word, or right before one
        ("Boil water. Add salt", 11, ("Boil water.", "Add salt")),
        ("Boil water. Add salt", 12, ("Boil water.", "Add salt")),
        # inside a word snaps back to the start of that word
        ("Boil water and salt", 7, ("Boil", "water and salt")),
        ("Boil water", 7, ("Boil", "water")),
        # after the first word and before the last are the limits
        ("Boil water", 4, ("Boil", "water")),
        ("Boil water", 5, ("Boil", "water")),
        # new lines count as whitespace
        ("Boil water\nAdd salt", 10, ("Boil water", "Add salt")),
    ],
)
def test_split_step_text(text: str, at: int, expected: tuple[str, str]):
    """The text splits at the cursor, trimmed on both sides."""
    assert split_step_text(text, at=at) == expected


@pytest.mark.parametrize(
    ("text", "at"),
    [
        ("Boil water", 0),  # before the first word
        ("Boil water", 2),  # inside the first word
        ("Boil water", 10),  # after the last word
        ("Boil water  ", 11),  # in trailing whitespace
        ("  Boil water", 1),  # in leading whitespace
        ("Boil", 2),  # a single word cannot be split
        ("Boil water", -1),
        ("Boil water", 99),
    ],
)
def test_split_step_text_refuses_senseless_cursor(text: str, at: int):
    """A cursor that would leave one half empty splits nothing."""
    assert split_step_text(text, at=at) is None
