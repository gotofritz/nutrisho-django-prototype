"""Tests for parsing the recipe search box (#32)."""

import re

import pytest

from recipes.utils.search_query import (
    MAX_TERMS,
    parse_query,
    term_variants,
    word_prefix_pattern,
)


def test_words_are_separate_terms():
    """`aubergine pasta` looks for either word."""
    parsed = parse_query("Aubergine pasta")
    assert parsed.terms == ["aubergine", "pasta"]
    assert parsed.excluded == []


def test_quotes_keep_a_phrase_together():
    """A quoted phrase is one term."""
    assert parse_query('"olive oil" garlic').terms == ["olive oil", "garlic"]


def test_a_leading_minus_excludes_a_term():
    """`-mushroom` and `-"blue cheese"` rule recipes out."""
    parsed = parse_query('pasta -mushroom -"blue cheese"')
    assert parsed.terms == ["pasta"]
    assert parsed.excluded == ["mushroom", "blue cheese"]


def test_repeats_and_blanks_are_dropped():
    """Case-insensitive repeats count once; empty quotes and a bare minus are ignored."""
    parsed = parse_query('Pasta pasta "" - "  "')
    assert parsed.terms == ["pasta"]
    assert parsed.excluded == []


def test_an_empty_query_is_empty():
    """Nothing typed means nothing to match."""
    parsed = parse_query("   ")
    assert not parsed
    assert parsed.terms == []


def test_a_query_with_only_exclusions_is_not_empty():
    """`-meat` alone still narrows the list."""
    assert parse_query("-meat")


def test_the_number_of_terms_is_capped():
    """Each term is a few subqueries, so a pasted paragraph cannot run away."""
    parsed = parse_query(" ".join(f"word{i}" for i in range(MAX_TERMS + 5)))
    assert len(parsed.terms) == MAX_TERMS


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("aubergine", ["aubergine"]),
        ("aubergines", ["aubergines", "aubergine"]),
        ("tomatoes", ["tomatoes", "tomatoe", "tomato"]),
        ("berries", ["berries", "berrie", "berry", "berri"]),
        ("chillies", ["chillies", "chillie", "chilly", "chilli"]),
        ("loaves", ["loaves", "loave", "loaf"]),
        ("peas", ["peas", "pea"]),
        ("gas", ["gas"]),
        ("olive oils", ["olive oils", "olive oil"]),
    ],
)
def test_variants_add_the_likely_singulars(term, expected):
    """A plural query finds the canonical singular the database holds."""
    assert term_variants(term) == expected


def test_the_pattern_matches_at_the_start_of_a_word_only():
    """`pea` finds peas and pea shoots, not chickpeas; `u` is not every word with a u."""
    pattern = re.compile(word_prefix_pattern("pea"), re.IGNORECASE)
    assert pattern.search("peas")
    assert pattern.search("Frozen pea shoots")
    assert pattern.search("(pea)")
    assert not pattern.search("chickpeas")


def test_the_pattern_escapes_regex_characters():
    """A term is literal text, never a regular expression."""
    pattern = re.compile(word_prefix_pattern("c++"), re.IGNORECASE)
    assert pattern.search("learn c++ cooking")
    assert not pattern.search("cc")
