"""Browser journey: merging ingredients in the staff clean-up tool (#63)."""

import pytest
from playwright.sync_api import Page, expect

from recipes.models import Ingredient, IngredientInRecipe

pytestmark = pytest.mark.e2e


def test_merging_two_ingredients_repoints_their_recipes(
    signed_in: Page, user, make_recipe, add_ingredient, make_ingredient
):
    """Tick two rows, Merge, pick the survivor: the recipe follows it."""
    user.is_staff = True
    user.save()
    recipe = make_recipe(owner=user, name="Ratatouille")
    courgette = make_ingredient("courgette")
    add_ingredient(recipe=recipe, ingredient=make_ingredient("zucchini"), quantity=2)
    signed_in.goto("/recipes/ingredients/manage/")
    merge = signed_in.locator("#action-merge")
    rows = signed_in.locator("#col-ingredients .ingredient-row")

    expect(merge).to_be_disabled()
    rows.filter(has_text="courgette").get_by_role("checkbox").check()
    rows.filter(has_text="zucchini").get_by_role("checkbox").check()
    expect(merge).to_be_enabled()
    merge.click()

    chooser = signed_in.locator(".merge-candidates")
    chooser.get_by_label("courgette").check()
    signed_in.locator(".panel-merge").click()

    expect(rows.filter(has_text="zucchini")).to_have_count(0)
    expect(rows.filter(has_text="courgette")).to_have_count(1)
    assert list(Ingredient.objects.values_list("ingredient_name", flat=True)) == ["courgette"]
    assert IngredientInRecipe.objects.get().ingredient == courgette
