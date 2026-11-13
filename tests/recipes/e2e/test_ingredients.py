"""Browser journeys: ingredient groups and ingredient rows on a recipe (#63)."""

import pytest
from playwright.sync_api import Page, expect

from recipes.models import IngredientGroup, Recipe
from tests.recipes.e2e.htmx import settled

pytestmark = pytest.mark.e2e


@pytest.fixture
def recipe(make_recipe, user) -> Recipe:
    """A recipe owned by the signed-in user."""
    return make_recipe(owner=user, name="Ragù")


def test_adding_an_ingredient_to_a_new_group(
    signed_in: Page, recipe, add_ingredient, make_ingredient
):
    """A new group saves in place and takes an ingredient, shown in its plural."""
    add_ingredient(recipe=recipe, ingredient=make_ingredient("beef"), quantity=500)
    signed_in.goto(f"/recipes/{recipe.pk}/")

    signed_in.get_by_role("button", name="+ Add group").click()
    name = signed_in.get_by_label("Group name")
    expect(name).to_be_focused()
    name.fill("Sauce")
    signed_in.locator("#groups-list .is-editing").get_by_role("button", name="Save").click()
    sauce = signed_in.locator(".group-block").filter(
        has=signed_in.get_by_role("heading", name="Sauce")
    )
    expect(sauce).to_be_visible()

    sauce.get_by_role("button", name="+ Add ingredient").click()
    quantity = signed_in.get_by_label("Quantity")
    expect(quantity).to_be_focused()
    settled(signed_in)
    quantity.fill("2")
    signed_in.get_by_label("Ingredient").fill("onion")
    signed_in.get_by_label("Chopped, blanched").fill("chopped")
    sauce.get_by_role("button", name="Save").click()

    expect(sauce.locator(".ingredient-content")).to_have_text("2 onions, chopped")
    group = IngredientGroup.objects.get(recipe=recipe, group_name="Sauce")
    assert [iir.ingredient.ingredient_name for iir in group.items.all()] == ["onion"]


def test_ticked_ingredients_move_to_a_group_made_on_the_page(
    signed_in: Page, recipe, add_ingredient, make_ingredient
):
    """The move panel's group list is refreshed out of band when a group is added."""
    add_ingredient(recipe=recipe, ingredient=make_ingredient("beef"), quantity=500)
    add_ingredient(recipe=recipe, ingredient=make_ingredient("tomato"), quantity=4)
    signed_in.goto(f"/recipes/{recipe.pk}/")
    panel = signed_in.locator("#reassign-panel")

    signed_in.get_by_role("button", name="+ Add group").click()
    signed_in.get_by_label("Group name").fill("Sauce")
    signed_in.locator("#groups-list .is-editing").get_by_role("button", name="Save").click()
    expect(signed_in.get_by_role("heading", name="Sauce")).to_be_visible()

    expect(panel).to_be_hidden()
    signed_in.locator(".ingredient-in-group-show", has_text="tomato").locator(
        ".ingredient-select"
    ).check()
    expect(panel).to_be_visible()
    panel.get_by_label("Move to:").select_option(label="Sauce")
    panel.get_by_role("button", name="Move").click()

    sauce = signed_in.locator(".group-block").filter(
        has=signed_in.get_by_role("heading", name="Sauce")
    )
    expect(sauce.locator(".ingredient-name")).to_have_text(["tomatoes"])
    expect(panel).to_be_hidden()
    group = IngredientGroup.objects.get(recipe=recipe, group_name="Sauce")
    assert [iir.ingredient.ingredient_name for iir in group.items.all()] == ["tomato"]


def test_typing_a_name_fills_the_suggestions(
    signed_in: Page, recipe, add_ingredient, make_ingredient
):
    """Each name input refills the shared datalist with matches for its own text (#80)."""
    add_ingredient(recipe=recipe, ingredient=make_ingredient("beef"), quantity=500)
    for name in ("onion", "spring onion", "shallot", "garlic"):
        make_ingredient(name)
    signed_in.goto(f"/recipes/{recipe.pk}/")

    signed_in.get_by_role("button", name="+ Add ingredient").click()
    expect(signed_in.get_by_label("Quantity")).to_be_focused()
    options = signed_in.locator("#ingredients-datalist option")
    expect(options).to_have_count(0)

    signed_in.get_by_label("Ingredient").press_sequentially("oni")
    expect(options).to_have_count(2)
    assert [o.get_attribute("value") for o in options.all()] == ["onion", "spring onion"]

    signed_in.get_by_label("Or:", exact=True).press_sequentially("sha")
    expect(options).to_have_count(1)
    expect(options).to_have_attribute("value", "shallot")


def test_a_group_s_move_buttons_sit_above_its_dotted_line(
    signed_in: Page, recipe, add_ingredient, make_ingredient
):
    """The ↑/↓ beside a group name stay above the dotted line that opens its list."""
    add_ingredient(recipe=recipe, ingredient=make_ingredient("beef"), quantity=500)
    signed_in.goto(f"/recipes/{recipe.pk}/")
    block = signed_in.locator(".group-block").first
    block.hover()

    line = block.locator(".ingredients-list").bounding_box()
    name = block.locator(".group-name").bounding_box()
    assert line and name
    for button in block.locator(".ingredient-group .move-btns button").all():
        box = button.bounding_box()
        assert box
        assert box["y"] + box["height"] <= line["y"], "button hangs over the dotted line"
    # The name itself still sits on the line, as on the printed sheet.
    assert name["y"] + name["height"] >= line["y"]
