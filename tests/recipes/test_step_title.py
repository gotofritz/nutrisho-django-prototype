"""Tests for the step-title splitting rule (plan 010, phase 2)."""

import pytest

from recipes.utils.step_title import sentence_case_heading, split_step_title


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # inline tag wrapper — the form the scraped recipes use
        ("<u>RAGÚ</u>: Sauté the beef", ("RAGÚ", "Sauté the beef")),
        ("<b>SAUCE</b>: Warm the milk", ("SAUCE", "Warm the milk")),
        ("<i>Sauce</i>: Warm the milk", ("Sauce", "Warm the milk")),
        ("<s>OLD</s>: Warm the milk", ("OLD", "Warm the milk")),
        # unwrapped, all upper case
        ("FOR THE STOCK: soak the kombu", ("FOR THE STOCK", "soak the kombu")),
        ("CAKE: Set oven to 180°", ("CAKE", "Set oven to 180°")),
        ("NORMAL POT: Soak dal 5 hours", ("NORMAL POT", "Soak dal 5 hours")),
        # digits and punctuation inside an otherwise upper-case run
        ("STEP 2 (OPTIONAL): rest the dough", ("STEP 2 (OPTIONAL)", "rest the dough")),
        # leading whitespace is tolerated
        ("  CAKE: cool it", ("CAKE", "cool it")),
    ],
)
def test_titles_are_split_off(text: str, expected: tuple[str, str]):
    assert split_step_title(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        # prose, not a heading — mixed case before the colon
        "Add salt: to taste",
        "Note: this is prose",
        # no whitespace after the colon
        "MIX 1:1 with water",
        # nothing left over once the heading is removed
        "<u>SAUCE</u>:",
        "SAUCE:",
        # no colon at all
        "Chop the onions",
        "CHOP THE ONIONS",
        # an unclosed or mismatched tag is left alone
        "<u>RAGÚ: Sauté the beef",
        "<u>RAGÚ</b>: Sauté the beef",
        # a tag that is not one of the four allowed inline tags
        "<em>RAGÚ</em>: Sauté the beef",
        # digits only, no letters
        "2: fold the dough",
        # too long to be a heading (max_length=128), wrapped or not
        f"{'A' * 129}: fold the dough",
        f"<u>{'A' * 129}</u>: fold the dough",
        # a wrapper around nothing is not a heading
        "<u> </u>: fold the dough",
    ],
)
def test_prose_is_left_whole(text: str):
    assert split_step_title(text) == ("", text)


def test_empty_string_stays_empty():
    assert split_step_title("") == ("", "")


def test_a_title_at_the_field_limit_is_split():
    title = "A" * 128
    assert split_step_title(f"{title}: fold") == (title, "fold")


@pytest.mark.parametrize(
    ("shouted", "expected"),
    [
        ("FOR THE STOCK", "For the stock"),
        ("IF MAKING OWN SPICE MIX", "If making own spice mix"),
        ("THE DAY BEFORE", "The day before"),
        ("NORMAL POT", "Normal pot"),
        ("RAGÚ", "Ragú"),
        ("CLASSIC NEGIMISO", "Classic negimiso"),
        # punctuation keeps its place; the first letter is the one raised
        ("(OPTIONAL) STEP", "(Optional) step"),
        ("STEP 2 (OPTIONAL)", "Step 2 (optional)"),
        ("GRETA'S RAGÙ", "Greta's ragù"),
        ("SLOW-COOK", "Slow-cook"),
    ],
)
def test_shouted_headings_are_sentence_cased(shouted: str, expected: str):
    assert sentence_case_heading(shouted) == expected


@pytest.mark.parametrize(
    "heading",
    [
        # already cased by hand — left exactly as written
        "Sauce",
        "For the stock",
        "Ragú",
        # nothing to case
        "",
        "2",
    ],
)
def test_headings_that_are_not_shouted_are_left_alone(heading: str):
    assert sentence_case_heading(heading) == heading
