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


def test_undo_takes_a_merge_back(
    signed_in: Page, user, make_recipe, add_ingredient, make_ingredient
):
    """Recent changes lists the merge; Undo brings the row back, ticked, recipe and all (#75)."""
    user.is_staff = True
    user.save()
    recipe = make_recipe(owner=user, name="Ratatouille")
    courgette = make_ingredient("courgette")
    zucchini = make_ingredient("zucchini")
    add_ingredient(recipe=recipe, ingredient=zucchini, quantity=2)
    signed_in.goto("/recipes/ingredients/manage/")
    rows = signed_in.locator("#col-ingredients .ingredient-row")
    rows.filter(has_text="courgette").get_by_role("checkbox").check()
    rows.filter(has_text="zucchini").get_by_role("checkbox").check()
    signed_in.locator("#action-merge").click()
    signed_in.locator(".merge-candidates").get_by_label("courgette").check()
    signed_in.locator(".panel-merge").click()

    history = signed_in.locator("#ingredient-changes")
    expect(history).to_contain_text("Merged “zucchini” into “courgette”")
    history.get_by_role("button", name="Undo").click()

    expect(rows.filter(has_text="zucchini").get_by_role("checkbox")).to_be_checked()
    expect(history).to_contain_text("undone")
    assert IngredientInRecipe.objects.get().ingredient == zucchini
    assert Ingredient.objects.filter(pk=courgette.pk).exists()


def test_show_more_appends_rows_and_closing_an_action_keeps_them(
    signed_in: Page, user, make_ingredient, monkeypatch
):
    """Show more adds the next page under the last row; closing an action keeps it (#80)."""
    from recipes.views import ingredient_admin

    monkeypatch.setattr(ingredient_admin, "PAGE_SIZE", 2)
    user.is_staff = True
    user.save()
    for name in ("apple", "banana", "cherry", "date", "elderberry"):
        make_ingredient(name)
    signed_in.goto("/recipes/ingredients/manage/")
    rows = signed_in.locator("#col-ingredients .ingredient-row")
    count = signed_in.locator("#ingredient-count .column-count")

    expect(rows).to_have_text(["apple", "banana"])
    signed_in.get_by_role("button", name="Show 2 more (2 of 5 shown)").click()
    expect(rows).to_have_text(["apple", "banana", "cherry", "date"])
    expect(rows.filter(has_text="cherry").get_by_role("checkbox")).to_be_focused()

    signed_in.locator("#select-all").check()
    expect(count).to_have_text("5 found / 4 selected")
    signed_in.locator("#action-edit").click()
    expect(signed_in.locator("#columns.workspace")).to_be_visible()
    signed_in.get_by_role("button", name="Done").click()
    expect(rows).to_have_text(["apple", "banana", "cherry", "date"])
    signed_in.get_by_role("button", name="Show 1 more (4 of 5 shown)").click()
    expect(rows).to_have_count(5)
    expect(signed_in.locator(".show-more")).to_have_count(0)
