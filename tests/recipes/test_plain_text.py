"""Tests for `plain_text`, the tag-free form of inline-HTML fields (#32)."""

import pytest

from recipes.utils.plain_text import plain_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Foo", "Foo"),
        ("<u>Foo</u>", "Foo"),
        ("<s>Old</s> <u>New</u> soup", "Old New soup"),
        ('<u class="x">Foo</u>', "Foo"),
        ("<u>unclosed", "unclosed"),
        ("stray</b> close", "stray close"),
        ("Fish &amp; chips", "Fish & chips"),
        ("Fish & chips", "Fish & chips"),
        ("oven<gas 4", "oven<gas 4"),
        ("line one<br>line two", "line one line two"),
        ("line one<br/>line two", "line one line two"),
        ("line one\nline two", "line one line two"),
        ("  padded   out  ", "padded out"),
        ("", ""),
    ],
)
def test_plain_text_drops_tags_and_keeps_the_words(raw, expected):
    """Tags go, text and entities stay, white space collapses to single spaces."""
    assert plain_text(raw) == expected
