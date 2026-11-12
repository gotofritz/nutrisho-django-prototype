"""Browser journey: showing a recipe for other servings (#63)."""

import re

import pytest
from playwright.sync_api import Page, expect

from recipes.models import IngredientInRecipe

pytestmark = pytest.mark.e2e


def test_showing_other_servings_scales_the_page_and_saves_nothing(
    signed_in: Page, user, make_recipe, add_ingredient, make_ingredient
):
    """The scale panel shows the page for 6 servings; Reset returns to the stored 4."""
    recipe = make_recipe(owner=user, name="Pancakes")
    add_ingredient(recipe=recipe, ingredient=make_ingredient("egg"), quantity=2)
    signed_in.goto(f"/recipes/{recipe.pk}/")

    signed_in.locator('[aria-controls="scale-panel"]').click()
    servings = signed_in.get_by_label("Show for")
    expect(servings).to_be_focused()
    servings.fill("6")
    signed_in.get_by_role("button", name="Show").click()

    expect(signed_in).to_have_url(re.compile(rf"/recipes/{recipe.pk}/\?servings=6$"))
    expect(signed_in.locator(".serves")).to_have_text("Serves 6")
    expect(signed_in.locator(".recipe-ingredients .ingredient-in-group-show")).to_have_text(
        ["3 eggs"]
    )
    assert IngredientInRecipe.objects.get().quantity == 2

    signed_in.get_by_role("link", name="Reset").click()
    expect(signed_in.locator(".recipe-ingredients .ingredient-content")).to_have_text(["2 eggs"])
