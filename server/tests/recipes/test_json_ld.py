"""Tests for reading schema.org Recipe JSON-LD as recipe sites publish it (#78)."""

import pytest

from recipes.utils.json_ld import (
    find_recipes,
    ingredient_lines,
    instruction_steps,
    servings_from_yield,
    text_of,
)


def test_find_recipes_in_a_bare_object():
    """A page's one Recipe object."""
    recipe = {"@context": "https://schema.org", "@type": "Recipe", "name": "Soup"}
    assert find_recipes(recipe) == [recipe]


def test_find_recipes_in_a_graph_and_a_list():
    """Yoast and friends put the Recipe in an @graph beside the page's other nodes."""
    soup = {"@type": "Recipe", "name": "Soup"}
    stew = {"@type": ["Recipe", "NewsArticle"], "name": "Stew"}
    data = [
        {"@graph": [{"@type": "WebPage"}, soup]},
        {"@type": "Article", "mainEntity": stew},
    ]
    assert find_recipes(data) == [soup, stew]


@pytest.mark.parametrize("type_", ["schema:Recipe", "http://schema.org/Recipe"])
def test_find_recipes_with_a_prefixed_type(type_: str):
    """A prefixed or full IRI type is still a Recipe."""
    recipe = {"@type": type_, "name": "Soup"}
    assert find_recipes(recipe) == [recipe]


def test_find_recipes_does_not_look_inside_a_recipe():
    """A recipe's own nested nodes are never recipes of their own."""
    recipe = {"@type": "Recipe", "isBasedOn": {"@type": "Recipe", "name": "Older soup"}}
    assert find_recipes(recipe) == [recipe]


def test_find_recipes_with_none():
    """Nothing that looks like a recipe gives an empty list."""
    assert find_recipes({"@type": "WebPage"}) == []
    assert find_recipes("Recipe") == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("4", 4),
        (4, 4),
        ("4 servings", 4),
        ("Serves 6-8", 6),
        (["4", "4 servings"], 4),
        ("Makes a lot", None),
        (None, None),
        (0, None),
        ("99999999", None),
    ],
)
def test_servings_from_yield(value: object, expected: int | None):
    """The first whole number a yield names, if the model can hold it."""
    assert servings_from_yield(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Soup &amp; bread", "Soup & bread"),
        (["Italian", "Sicilian"], "Italian"),
        ({"@id": "https://example.com/r/1"}, "https://example.com/r/1"),
        (None, ""),
        (3, "3"),
        ("<p>Rich</p>\n<p>and warm</p>", "Rich and warm"),
    ],
)
def test_text_of(value: object, expected: str):
    """A text property's first value, without markup."""
    assert text_of(value) == expected


def test_ingredient_lines():
    """One line per entry, blanks dropped; a lone string is one line."""
    assert ingredient_lines(["2 onions", " ", "<b>1 tsp</b> salt"]) == ["2 onions", "1 tsp salt"]
    assert ingredient_lines("2 onions") == ["2 onions"]
    assert ingredient_lines(None) == []


def test_instruction_steps_from_text():
    """A block of text is one step per line or paragraph."""
    text = "<p>Chop the onions.</p><p>Fry them.</p>\n\nServe."
    assert instruction_steps(text) == [
        ("", "Chop the onions."),
        ("", "Fry them."),
        ("", "Serve."),
    ]


def test_instruction_steps_from_how_to_steps():
    """HowToStep text, with a name that says more than the text as its title."""
    value = [
        {"@type": "HowToStep", "text": "Chop the onions."},
        {"@type": "HowToStep", "name": "Chop the onions.", "text": "Chop the onions."},
        {"@type": "HowToStep", "name": "Step 3", "text": "Fry them."},
        {"@type": "HowToStep", "name": "Fry", "text": "Fry them until golden."},
        {"@type": "HowToStep", "name": "Serve hot."},
        "Eat.",
    ]
    assert instruction_steps(value) == [
        ("", "Chop the onions."),
        ("", "Chop the onions."),
        ("", "Fry them."),
        ("Fry", "Fry them until golden."),
        ("", "Serve hot."),
        ("", "Eat."),
    ]


def test_instruction_steps_from_sections():
    """A HowToSection's name is the title of its first step."""
    value = [
        {
            "@type": "HowToSection",
            "name": "For the sauce",
            "itemListElement": [
                {"@type": "HowToStep", "text": "Melt the butter."},
                {"@type": "HowToStep", "text": "Whisk in flour."},
            ],
        },
        {
            "@type": "HowToSection",
            "name": "To serve",
            "itemListElement": {"@type": "HowToStep", "text": "Pour."},
        },
    ]
    assert instruction_steps(value) == [
        ("For the sauce", "Melt the butter."),
        ("", "Whisk in flour."),
        ("To serve", "Pour."),
    ]


def test_instruction_steps_with_none():
    """No instructions, no steps."""
    assert instruction_steps(None) == []
    assert instruction_steps([{"@type": "HowToStep"}]) == []
