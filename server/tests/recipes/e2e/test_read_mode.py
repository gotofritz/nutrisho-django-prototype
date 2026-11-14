"""Browser journeys: reading a recipe, switching to edit, editing from the keyboard (#58, #60)."""

import pytest
from playwright.sync_api import Page, expect

from recipes.models import Recipe, Step
from tests.recipes.e2e.htmx import settled

pytestmark = pytest.mark.e2e


@pytest.fixture
def recipe(make_recipe, user, add_step, add_ingredient, make_ingredient) -> Recipe:
    """A recipe with a step and an ingredient, owned by the signed-in user."""
    recipe = make_recipe(owner=user, name="Risotto")
    add_step(recipe=recipe, text="Toast the rice.")
    add_ingredient(recipe=recipe, ingredient=make_ingredient("rice"))
    return recipe


def test_a_tap_while_reading_opens_no_editor(signed_in: Page, recipe):
    """A tap on a line, as when scrolling on a tablet, leaves the recipe as it is."""
    signed_in.goto(f"/recipes/{recipe.pk}/")

    signed_in.get_by_text("Toast the rice.").click()
    signed_in.locator(".ingredient-name").click()

    settled(signed_in)
    expect(signed_in.locator(".is-editing")).to_have_count(0)


def test_edit_recipe_switches_to_editing_and_back(signed_in: Page, recipe):
    """The margin's toggle is the way into edit mode and out of it."""
    signed_in.goto(f"/recipes/{recipe.pk}/")

    signed_in.get_by_role("link", name="Edit recipe").click()
    signed_in.get_by_role("button", name="Toast the rice.", exact=True).click()
    expect(signed_in.get_by_placeholder("Title (optional)")).to_be_focused()

    signed_in.get_by_role("link", name="Done editing").click()
    expect(signed_in.get_by_role("link", name="Edit recipe")).to_be_visible()
    expect(signed_in.get_by_role("button", name="Toast the rice.", exact=True)).to_have_count(0)


def test_the_keyboard_opens_an_editor_and_escape_cancels_it(signed_in: Page, recipe):
    """Enter on a line opens its editor; Escape puts the line back and focus on it."""
    signed_in.goto(f"/recipes/{recipe.pk}/?edit=1")
    line = signed_in.get_by_role("button", name="Toast the rice.", exact=True)

    line.focus()
    signed_in.keyboard.press("Enter")
    title = signed_in.get_by_placeholder("Title (optional)")
    expect(title).to_be_focused()
    settled(signed_in)
    title.fill("Changed my mind")
    signed_in.keyboard.press("Escape")

    expect(signed_in.locator(".is-editing")).to_have_count(0)
    expect(line).to_be_focused()
    assert Step.objects.get(recipe=recipe).step_title == ""


def test_escape_drops_an_unsaved_draft(signed_in: Page, recipe):
    """A new step's draft goes on Escape too, without a request."""
    signed_in.goto(f"/recipes/{recipe.pk}/?edit=1")

    signed_in.get_by_role("button", name="+ Add step").click()
    expect(signed_in.get_by_placeholder("Title (optional)")).to_be_focused()
    settled(signed_in)
    signed_in.keyboard.press("Escape")

    expect(signed_in.locator(".is-editing")).to_have_count(0)
    assert Step.objects.filter(recipe=recipe).count() == 1


@pytest.mark.parametrize("mode", ["", "?edit=1"])
def test_a_phone_gets_a_plain_list_with_the_ingredients_first(signed_in: Page, recipe, mode: str):
    """On a phone: no sideways scroll, no Lobster title, ingredients above the steps."""
    signed_in.set_viewport_size({"width": 390, "height": 844})
    signed_in.goto(f"/recipes/{recipe.pk}/{mode}")

    overflow = signed_in.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow == 0
    title_font = signed_in.locator(".recipe-title").evaluate("e => getComputedStyle(e).fontFamily")
    assert "Lobster" not in title_font
    ingredients = signed_in.locator(".recipe-ingredients").bounding_box()
    steps = signed_in.locator("#steps-list").bounding_box()
    assert ingredients and steps
    assert ingredients["y"] < steps["y"]
