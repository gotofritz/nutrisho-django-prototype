"""Tests for the ingredient-admin HTMX views (Plan 007)."""

import re
from decimal import Decimal

import pytest

from recipes.models import Ingredient

MANAGE_URL = "/recipes/ingredients/manage/"
SEARCH_URL = "/recipes/ingredients/manage/search/"


def squash(html: str) -> str:
    """Collapse runs of whitespace so assertions ignore template line breaks."""
    return re.sub(r"\s+", " ", html)


def has_bare_attr(tag_text: str, name: str) -> bool:
    """True if the tag carries `name` as a boolean attribute.

    Not a substring test: the buttons also carry Tailwind variant classes like
    `disabled:opacity-40`, which would satisfy `"disabled" in tag`.
    """
    return re.search(rf"\s{name}(?=[\s>])", tag_text) is not None


def tag(html: str, element_id: str) -> str:
    """The opening tag carrying the given id, for attribute assertions."""
    match = re.search(rf"<[^>]*\bid=\"{element_id}\"[^>]*>", html)
    assert match is not None, f"no element with id={element_id!r}"
    return match.group(0)


@pytest.mark.django_db
def test_manager_redirects_anonymous_user_to_login(client):
    response = client.get(MANAGE_URL)
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_manager_returns_200_for_authenticated_user(auth_client):
    assert auth_client.get(MANAGE_URL).status_code == 200


@pytest.mark.django_db
def test_manager_renders_the_four_columns(auth_client):
    html = auth_client.get(MANAGE_URL).content.decode()
    for element_id in ("col-actions", "col-ingredients", "col-recipes", "col-preview"):
        assert tag(html, element_id)


@pytest.mark.django_db
def test_manager_back_link_goes_somewhere_the_user_can_actually_reach(auth_client):
    """The tool is login-only, so back must not land on the staff-gated admin."""
    html = auth_client.get(MANAGE_URL).content.decode()
    assert 'href="/recipes/"' in html
    assert 'href="/admin/"' not in html


@pytest.mark.django_db
def test_manager_has_search_input(auth_client):
    html = auth_client.get(MANAGE_URL).content.decode()
    assert 'name="q"' in html


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["edit", "delete", "merge"])
def test_manager_action_buttons_start_disabled(auth_client, action):
    html = auth_client.get(MANAGE_URL).content.decode()
    assert has_bare_attr(tag(html, f"action-{action}"), "disabled")


@pytest.mark.django_db
def test_search_requires_login(client):
    response = client.get(SEARCH_URL)
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_search_lists_all_ingredients_case_insensitively_sorted(auth_client, make_ingredient):
    make_ingredient("onion")
    make_ingredient("Carrot")
    make_ingredient("aubergine")
    html = auth_client.get(SEARCH_URL).content.decode()
    positions = [html.index(name) for name in ("aubergine", "Carrot", "onion")]
    assert positions == sorted(positions)


@pytest.mark.django_db
def test_search_renders_a_checkbox_per_ingredient(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    carrot = make_ingredient("carrot")
    html = squash(auth_client.get(SEARCH_URL).content.decode())
    for ingredient in (onion, carrot):
        assert f'name="ingredient_ids" value="{ingredient.pk}"' in html
    # Not every checkbox: the column header carries the tri-state select-all box.
    assert html.count('class="ingredient-pick"') == 2


@pytest.mark.django_db
def test_search_filters_by_query(auth_client, make_ingredient):
    make_ingredient("onion")
    make_ingredient("aubergine")
    html = auth_client.get(SEARCH_URL, {"q": "ONI"}).content.decode()
    assert "onion" in html
    assert "aubergine" not in html


@pytest.mark.django_db
def test_search_header_reports_found_and_selected_counts(auth_client, make_ingredient):
    make_ingredient("onion")
    make_ingredient("aubergine")
    html = auth_client.get(SEARCH_URL).content.decode()
    assert "2 found / 0 selected" in html


@pytest.mark.django_db
def test_search_column_carries_width_scroll_and_wrap_classes(auth_client):
    html = auth_client.get(SEARCH_URL).content.decode()
    column = tag(html, "col-ingredients")
    assert "max-w-[38ch]" in column
    assert "h-full" in column
    assert "min-h-0" in column
    assert "overflow-y-auto" in column
    assert "overflow-x-hidden" in column
    assert "break-words" in column


@pytest.mark.django_db
def test_search_on_empty_database_returns_200(auth_client):
    response = auth_client.get(SEARCH_URL)
    assert response.status_code == 200
    assert "0 found / 0 selected" in response.content.decode()


RECIPES_URL = "/recipes/ingredients/manage/recipes/"


def preview_url(recipe_pk: int) -> str:
    return f"/recipes/ingredients/manage/preview/{recipe_pk}/"


@pytest.mark.django_db
def test_matches_requires_login(client):
    response = client.get(RECIPES_URL)
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_matches_lists_recipes_using_the_selected_ingredients(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    make_recipe(owner=user, name="Pancakes")
    add_ingredient(recipe=moussaka, ingredient=onion)
    html = auth_client.get(RECIPES_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    assert "Moussaka" in html
    assert "Pancakes" not in html


@pytest.mark.django_db
def test_matches_renders_no_checkboxes(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    html = auth_client.get(RECIPES_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    # Only column 3 itself: the response also carries the out-of-band column-2
    # header, which does hold the tri-state select-all box.
    column = html.split('id="ingredient-count"')[0]
    assert 'type="checkbox"' not in column


@pytest.mark.django_db
def test_matches_header_reports_matches_and_selected_counts(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    aubergine = make_ingredient("aubergine")
    moussaka = make_recipe(owner=user, name="Moussaka")
    ratatouille = make_recipe(owner=user, name="Ratatouille")
    add_ingredient(recipe=moussaka, ingredient=onion)
    add_ingredient(recipe=ratatouille, ingredient=aubergine)
    response = auth_client.get(RECIPES_URL, {"ingredient_ids": [onion.pk, aubergine.pk]})
    assert "2 matches / 2 selected" in response.content.decode()


@pytest.mark.django_db
def test_matches_with_empty_selection_lists_nothing(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    html = auth_client.get(RECIPES_URL).content.decode()
    assert "0 matches / 0 selected" in html
    assert "Moussaka" not in html


@pytest.mark.django_db
def test_matches_column_carries_width_scroll_and_wrap_classes(auth_client):
    html = auth_client.get(RECIPES_URL).content.decode()
    column = tag(html, "col-recipes")
    assert "max-w-[62ch]" in column
    assert "h-full" in column
    assert "min-h-0" in column
    assert "overflow-y-auto" in column
    assert "overflow-x-hidden" in column
    assert "break-words" in column


@pytest.mark.django_db
def test_matches_rows_link_to_the_recipe_preview(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    html = auth_client.get(RECIPES_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    assert f'hx-get="{preview_url(moussaka.pk)}"' in html


@pytest.mark.django_db
def test_matches_excludes_another_owners_recipes(
    auth_client, other_user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    theirs = make_recipe(owner=other_user, name="Their Soup")
    add_ingredient(recipe=theirs, ingredient=onion)
    html = auth_client.get(RECIPES_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    assert "Their Soup" not in html


@pytest.mark.django_db
def test_preview_requires_login(client, user, make_recipe):
    moussaka = make_recipe(owner=user, name="Moussaka")
    response = client.get(preview_url(moussaka.pk))
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_preview_shows_name_servings_ingredients_and_steps(
    auth_client, user, make_ingredient, make_recipe, add_ingredient, add_step
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    add_step(recipe=moussaka, text="Slice the aubergine")
    html = auth_client.get(preview_url(moussaka.pk)).content.decode()
    assert "Moussaka" in html
    assert "Serves 4" in html
    assert "Main" in html
    assert "onion" in html
    assert "Slice the aubergine" in html


@pytest.mark.django_db
def test_preview_has_no_navigation_or_edit_controls(
    auth_client, user, make_ingredient, make_recipe, add_ingredient, add_step
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    add_step(recipe=moussaka, text="Slice the aubergine")
    html = auth_client.get(preview_url(moussaka.pk)).content.decode()
    assert "/edit/" not in html
    assert "navbar" not in html
    assert "hx-post" not in html
    assert "<button" not in html


@pytest.mark.django_db
def test_preview_404s_for_another_owners_recipe(auth_client, other_user, make_recipe):
    theirs = make_recipe(owner=other_user, name="Their Soup")
    assert auth_client.get(preview_url(theirs.pk)).status_code == 404


CANCEL_URL = "/recipes/ingredients/manage/cancel/"
EDIT_URL = "/recipes/ingredients/manage/edit/"
DELETE_URL = "/recipes/ingredients/manage/delete/"
MERGE_URL = "/recipes/ingredients/manage/merge/"


@pytest.mark.django_db
def test_search_echoes_the_selection_as_checked(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    carrot = make_ingredient("carrot")
    html = squash(auth_client.get(SEARCH_URL, {"ingredient_ids": [onion.pk]}).content.decode())
    assert f'value="{onion.pk}" checked' in html
    assert f'value="{carrot.pk}" checked' not in html


@pytest.mark.django_db
def test_search_header_counts_the_selection(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    make_ingredient("carrot")
    html = auth_client.get(SEARCH_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    assert "2 found / 1 selected" in html


@pytest.mark.django_db
def test_search_ignores_non_numeric_selection_values(auth_client, make_ingredient):
    make_ingredient("onion")
    html = auth_client.get(SEARCH_URL, {"ingredient_ids": ["oops"]}).content.decode()
    assert "1 found / 0 selected" in html


@pytest.mark.django_db
def test_ingredient_column_refreshes_matches_on_selection_change(auth_client):
    """The trigger is scoped to row checkboxes, not any change in the column.

    The header's select-all box lives inside this element and issues its own
    request; an unscoped `change` fires both at once, and whichever response
    lands second finds its out-of-band targets already gone.
    """
    column = tag(squash(auth_client.get(SEARCH_URL).content.decode()), "col-ingredients")
    assert f'hx-get="{RECIPES_URL}"' in column
    assert "hx-trigger=\"change[target.classList.contains('ingredient-pick')]\"" in column
    assert 'hx-target="#col-recipes"' in column


@pytest.mark.django_db
def test_matches_response_refreshes_the_column_two_count_out_of_band(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    make_ingredient("carrot")
    html = squash(auth_client.get(RECIPES_URL, {"ingredient_ids": [onion.pk]}).content.decode())
    assert 'id="ingredient-count"' in html
    assert 'hx-swap-oob="true"' in html
    assert "2 found / 1 selected" in html


@pytest.mark.django_db
def test_matches_out_of_band_count_respects_the_active_query(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    make_ingredient("carrot")
    html = auth_client.get(RECIPES_URL, {"q": "oni", "ingredient_ids": [onion.pk]})
    assert "1 found / 1 selected" in html.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("url", [EDIT_URL, DELETE_URL])
def test_edit_and_delete_reject_an_empty_selection(auth_client, url):
    response = auth_client.get(url)
    assert response.status_code == 422
    assert "at least 1 ingredient" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("selected", [0, 1])
def test_merge_rejects_fewer_than_two_selected(auth_client, make_ingredient, selected):
    ids = [make_ingredient(f"ingredient {i}").pk for i in range(selected)]
    response = auth_client.get(MERGE_URL, {"ingredient_ids": ids})
    assert response.status_code == 422
    assert "at least 2 ingredients" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("url", [EDIT_URL, DELETE_URL])
def test_edit_and_delete_accept_one_selected(auth_client, make_ingredient, url):
    onion = make_ingredient("onion")
    response = auth_client.get(url, {"ingredient_ids": [onion.pk]})
    assert response.status_code == 200


@pytest.mark.django_db
def test_merge_accepts_two_selected(auth_client, make_ingredient):
    ids = [make_ingredient("onion").pk, make_ingredient("onions").pk]
    assert auth_client.get(MERGE_URL, {"ingredient_ids": ids}).status_code == 200


@pytest.mark.django_db
def test_cancel_requires_login(client):
    response = client.get(CANCEL_URL)
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_cancel_restores_the_three_columns(auth_client):
    html = auth_client.get(CANCEL_URL).content.decode()
    for element_id in ("columns", "col-ingredients", "col-recipes", "col-preview"):
        assert tag(html, element_id)


@pytest.mark.django_db
def test_cancel_preserves_query_selection_and_counts(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    make_ingredient("carrot")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    response = auth_client.get(CANCEL_URL, {"q": "oni", "ingredient_ids": [onion.pk]})
    html = squash(response.content.decode())
    assert f'value="{onion.pk}" checked' in html
    assert "1 found / 1 selected" in html
    assert "1 matches / 1 selected" in html
    assert "carrot" not in html


def save_url(ingredient_pk: int) -> str:
    return f"/recipes/ingredients/manage/{ingredient_pk}/save/"


@pytest.mark.django_db
def test_edit_renders_one_prefilled_panel_per_selected_ingredient(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    carrot = make_ingredient("carrot")
    make_ingredient("aubergine")
    html = auth_client.get(EDIT_URL, {"ingredient_ids": [onion.pk, carrot.pk]}).content.decode()
    assert html.count("<form") == 2
    assert 'value="onion"' in html
    assert 'value="carrot"' in html
    assert 'value="aubergine"' not in html


@pytest.mark.django_db
def test_edit_panel_posts_to_its_own_save_url(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    html = auth_client.get(EDIT_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    assert f'hx-post="{save_url(onion.pk)}"' in html


@pytest.mark.django_db
def test_edit_workspace_carries_the_selection_as_hidden_inputs(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    carrot = make_ingredient("carrot")
    html = squash(
        auth_client.get(EDIT_URL, {"ingredient_ids": [onion.pk, carrot.pk]}).content.decode()
    )
    assert tag(html, "workspace-selection")
    for ingredient in (onion, carrot):
        assert f'name="ingredient_ids" value="{ingredient.pk}"' in html
    assert html.count('type="hidden" class="workspace-pick"') == 2


@pytest.mark.django_db
def test_edit_turns_the_clicked_button_into_cancel(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    html = squash(auth_client.get(EDIT_URL, {"ingredient_ids": [onion.pk]}).content.decode())
    assert 'hx-swap-oob="true"' in html
    assert "action-cancel" in tag(html, "action-edit")
    assert f'hx-get="{CANCEL_URL}"' in html


@pytest.mark.django_db
def test_save_requires_login(client, make_ingredient):
    onion = make_ingredient("onion")
    response = client.post(save_url(onion.pk), {"ingredient_name": "onions"})
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_save_rejects_get(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    assert auth_client.get(save_url(onion.pk)).status_code == 405


@pytest.mark.django_db
def test_save_persists_the_rename_and_closes_the_lone_panel(auth_client, make_ingredient):
    """One panel is the whole workspace, so re-rendering it looks like a no-op."""
    onion = make_ingredient("onion")
    response = auth_client.post(
        save_url(onion.pk),
        {"ingredient_name": "spring onion", "family": "VEG", "ingredient_ids": [onion.pk]},
    )
    assert response.status_code == 200
    onion.refresh_from_db()
    assert onion.ingredient_name == "spring onion"
    html = response.content.decode()
    assert response["HX-Retarget"] == "#columns"
    assert response["HX-Reswap"] == "outerHTML"
    assert tag(html, "col-ingredients")
    assert "spring onion" in html
    assert "<form" not in html


@pytest.mark.django_db
def test_save_closes_the_workspace_even_without_a_carried_selection(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    response = auth_client.post(save_url(onion.pk), {"ingredient_name": "onions"})
    assert response["HX-Retarget"] == "#columns"


@pytest.mark.django_db
def test_save_keeps_the_other_panels_open_when_several_are_being_edited(
    auth_client, make_ingredient
):
    """Closing on the first save would discard whatever is typed in the siblings."""
    onion = make_ingredient("onion")
    carrot = make_ingredient("carrot")
    response = auth_client.post(
        save_url(onion.pk),
        {"ingredient_name": "spring onion", "ingredient_ids": [onion.pk, carrot.pk]},
    )
    assert response.status_code == 200
    html = response.content.decode()
    assert "HX-Retarget" not in response
    assert f'id="ingredient-panel-{onion.pk}"' in html
    assert "Saved" in html
    assert 'id="col-ingredients"' not in html


@pytest.mark.django_db
def test_save_panel_carries_the_selection_so_it_knows_how_many_are_open(
    auth_client, make_ingredient
):
    onion = make_ingredient("onion")
    html = auth_client.get(EDIT_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    assert 'hx-include=".workspace-pick, #ingredient-search, #unused-only, #plurals-only"' in html


@pytest.mark.django_db
def test_edit_exit_button_reads_done_not_cancel(auth_client, make_ingredient):
    """Each panel saves itself, so leaving the edit workspace discards nothing."""
    onion = make_ingredient("onion")
    html = auth_client.get(EDIT_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    assert ">Done</button>" in html


@pytest.mark.django_db
@pytest.mark.parametrize("url", [DELETE_URL, MERGE_URL])
def test_destructive_workspaces_still_say_cancel(auth_client, make_ingredient, url):
    ids = [make_ingredient("onion").pk, make_ingredient("carrot").pk]
    html = auth_client.get(url, {"ingredient_ids": ids}).content.decode()
    assert ">Cancel</button>" in html


@pytest.mark.django_db
def test_save_rename_shows_up_in_the_ingredient_column(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    auth_client.post(save_url(onion.pk), {"ingredient_name": "spring onion"})
    html = auth_client.get(SEARCH_URL).content.decode()
    assert "spring onion" in html


@pytest.mark.django_db
def test_save_returns_only_the_panel_it_was_asked_for(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    carrot = make_ingredient("carrot")
    html = auth_client.post(
        save_url(onion.pk),
        {"ingredient_name": "onions", "ingredient_ids": [onion.pk, carrot.pk]},
    ).content.decode()
    assert f'id="ingredient-panel-{onion.pk}"' in html
    assert f'id="ingredient-panel-{carrot.pk}"' not in html


@pytest.mark.django_db
def test_save_404s_for_an_unknown_ingredient(auth_client):
    assert auth_client.post(save_url(9999), {"ingredient_name": "onions"}).status_code == 404


@pytest.mark.django_db
def test_save_with_a_clashing_name_returns_errors_and_does_not_write(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    make_ingredient("Aubergine")
    response = auth_client.post(save_url(onion.pk), {"ingredient_name": "aubergine"})
    assert "merge them instead" in response.content.decode()
    onion.refresh_from_db()
    assert onion.ingredient_name == "onion"


@pytest.mark.django_db
def test_delete_confirm_lists_the_selected_ingredients(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    carrot = make_ingredient("carrot")
    html = auth_client.get(DELETE_URL, {"ingredient_ids": [onion.pk, carrot.pk]}).content.decode()
    assert "onion" in html
    assert "carrot" in html


@pytest.mark.django_db
def test_delete_confirm_offers_no_replacement_picker_when_nothing_uses_them(
    auth_client, make_ingredient
):
    onion = make_ingredient("onion")
    html = auth_client.get(DELETE_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    assert 'name="replacement_id"' not in html


@pytest.mark.django_db
def test_delete_confirm_shows_affected_count_and_replacement_picker_when_used(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    make_ingredient("shallot")
    for name in ("Moussaka", "Ratatouille"):
        add_ingredient(recipe=make_recipe(owner=user, name=name), ingredient=onion)
    html = auth_client.get(DELETE_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    assert "2 recipes" in html
    assert 'name="replacement_id"' in html
    assert "shallot" in html


@pytest.mark.django_db
def test_delete_confirm_replacement_choices_exclude_the_victims(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    make_ingredient("shallot")
    add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=onion)
    html = auth_client.get(DELETE_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    picker = html.split('name="replacement_id"', 1)[1].split("</select>", 1)[0]
    assert "shallot" in picker
    assert "onion" not in picker


@pytest.mark.django_db
def test_delete_post_removes_unused_ingredients_and_refreshes_the_column(
    auth_client, make_ingredient
):
    onion = make_ingredient("onion")
    make_ingredient("carrot")
    response = auth_client.post(DELETE_URL, {"ingredient_ids": [onion.pk]})
    assert response.status_code == 200
    html = response.content.decode()
    assert not Ingredient.objects.filter(pk=onion.pk).exists()
    assert "1 found / 0 selected" in html
    assert "onion" not in html


@pytest.mark.django_db
def test_delete_post_with_a_replacement_repoints_and_deletes(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    shallot = make_ingredient("shallot")
    iir = add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=onion)
    response = auth_client.post(
        DELETE_URL, {"ingredient_ids": [onion.pk], "replacement_id": shallot.pk}
    )
    assert response.status_code == 200
    iir.refresh_from_db()
    assert iir.ingredient_id == shallot.pk
    assert not Ingredient.objects.filter(pk=onion.pk).exists()


@pytest.mark.django_db
def test_delete_post_without_a_replacement_is_blocked_and_deletes_nothing(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    make_ingredient("shallot")
    add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=onion)
    response = auth_client.post(DELETE_URL, {"ingredient_ids": [onion.pk]})
    assert response.status_code == 422
    html = response.content.decode()
    assert "pick a replacement" in html
    assert 'name="replacement_id"' in html
    assert Ingredient.objects.filter(pk=onion.pk).exists()


@pytest.mark.django_db
def test_delete_post_requires_login(client, make_ingredient):
    onion = make_ingredient("onion")
    response = client.post(DELETE_URL, {"ingredient_ids": [onion.pk]})
    assert response.status_code == 302
    assert Ingredient.objects.filter(pk=onion.pk).exists()


@pytest.mark.django_db
def test_merge_chooser_offers_a_survivor_radio_per_selected_ingredient(
    auth_client, make_ingredient
):
    aubergine = make_ingredient("aubergine")
    eggplant = make_ingredient("eggplant")
    html = squash(
        auth_client.get(MERGE_URL, {"ingredient_ids": [aubergine.pk, eggplant.pk]}).content.decode()
    )
    assert html.count('type="radio" name="survivor_id"') == 2
    for ingredient in (aubergine, eggplant):
        assert f'name="survivor_id" value="{ingredient.pk}"' in html


@pytest.mark.django_db
def test_merge_chooser_defaults_to_the_first_candidate(auth_client, make_ingredient):
    aubergine = make_ingredient("aubergine")
    eggplant = make_ingredient("eggplant")
    html = squash(
        auth_client.get(MERGE_URL, {"ingredient_ids": [eggplant.pk, aubergine.pk]}).content.decode()
    )
    assert f'name="survivor_id" value="{aubergine.pk}" checked' in html


@pytest.mark.django_db
def test_merge_post_collapses_the_rows_and_keeps_the_survivor_selected(
    auth_client, make_ingredient
):
    aubergine = make_ingredient("aubergine")
    eggplant = make_ingredient("eggplant")
    response = auth_client.post(
        MERGE_URL,
        {"ingredient_ids": [aubergine.pk, eggplant.pk], "survivor_id": aubergine.pk},
    )
    assert response.status_code == 200
    html = squash(response.content.decode())
    assert not Ingredient.objects.filter(pk=eggplant.pk).exists()
    assert "1 found / 1 selected" in html
    assert f'value="{aubergine.pk}" checked' in html


@pytest.mark.django_db
def test_merge_post_moves_recipes_onto_the_survivor(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    aubergine = make_ingredient("aubergine")
    eggplant = make_ingredient("eggplant")
    iir = add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=eggplant)
    auth_client.post(
        MERGE_URL,
        {"ingredient_ids": [aubergine.pk, eggplant.pk], "survivor_id": aubergine.pk},
    )
    iir.refresh_from_db()
    assert iir.ingredient_id == aubergine.pk


@pytest.mark.django_db
def test_merge_post_rejects_a_survivor_outside_the_selection(auth_client, make_ingredient):
    aubergine = make_ingredient("aubergine")
    eggplant = make_ingredient("eggplant")
    outsider = make_ingredient("courgette")
    response = auth_client.post(
        MERGE_URL,
        {"ingredient_ids": [aubergine.pk, eggplant.pk], "survivor_id": outsider.pk},
    )
    assert response.status_code == 422
    assert "which ingredient to keep" in response.content.decode()
    assert Ingredient.objects.count() == 3


@pytest.mark.django_db
def test_merge_post_without_a_survivor_is_rejected(auth_client, make_ingredient):
    ids = [make_ingredient("aubergine").pk, make_ingredient("eggplant").pk]
    response = auth_client.post(MERGE_URL, {"ingredient_ids": ids})
    assert response.status_code == 422
    assert Ingredient.objects.count() == 2


@pytest.mark.django_db
def test_merge_post_404s_for_an_unknown_survivor(auth_client, make_ingredient):
    aubergine = make_ingredient("aubergine")
    response = auth_client.post(
        MERGE_URL, {"ingredient_ids": [aubergine.pk, 9999], "survivor_id": 9999}
    )
    assert response.status_code == 404
    assert Ingredient.objects.filter(pk=aubergine.pk).exists()


@pytest.mark.django_db
def test_merge_post_with_fewer_than_two_selected_is_blocked(auth_client, make_ingredient):
    aubergine = make_ingredient("aubergine")
    response = auth_client.post(
        MERGE_URL, {"ingredient_ids": [aubergine.pk], "survivor_id": aubergine.pk}
    )
    assert response.status_code == 422
    assert Ingredient.objects.filter(pk=aubergine.pk).exists()


@pytest.mark.django_db
def test_merge_post_requires_login(client, make_ingredient):
    ids = [make_ingredient("aubergine").pk, make_ingredient("eggplant").pk]
    response = client.post(MERGE_URL, {"ingredient_ids": ids, "survivor_id": ids[0]})
    assert response.status_code == 302
    assert Ingredient.objects.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("url", [EDIT_URL, DELETE_URL])
def test_action_panels_collapse_the_columns_into_a_full_width_workspace(
    auth_client, make_ingredient, url
):
    onion = make_ingredient("onion")
    html = auth_client.get(url, {"ingredient_ids": [onion.pk]}).content.decode()
    workspace = tag(html, "columns")
    assert "workspace" in workspace
    assert "grow" in workspace
    assert "h-full" in workspace
    assert "overflow-y-auto" in workspace
    for column in ("col-ingredients", "col-recipes", "col-preview"):
        assert f'id="{column}"' not in html


@pytest.mark.django_db
def test_recipe_list_links_to_the_clean_up_tool(auth_client):
    html = auth_client.get("/recipes/").content.decode()
    assert MANAGE_URL in html


@pytest.mark.django_db
def test_admin_ingredient_changelist_links_to_the_clean_up_tool(admin_client):
    html = admin_client.get("/admin/recipes/ingredient/").content.decode()
    assert MANAGE_URL in html


@pytest.mark.django_db
def test_preview_opens_the_recipe_in_a_new_tab(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    """The preview is read-only, so editing has to happen somewhere else.

    A new tab, so the clean-up selection behind it survives.
    """
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    html = squash(auth_client.get(preview_url(moussaka.pk)).content.decode())
    assert f'href="/recipes/{moussaka.pk}/"' in html
    assert 'target="_blank"' in html
    assert 'rel="noopener"' in html


@pytest.mark.django_db
def test_preview_edit_link_sits_above_the_recipe(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    html = auth_client.get(preview_url(moussaka.pk)).content.decode()
    assert html.index('target="_blank"') < html.index("preview-title")


@pytest.mark.django_db
def test_preview_edit_link_is_not_boosted(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    """hx-boost on <body> would otherwise swap the page in place of the tab."""
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    html = squash(auth_client.get(preview_url(moussaka.pk)).content.decode())
    assert 'hx-boost="false"' in html


@pytest.mark.django_db
def test_preview_without_a_recipe_shows_no_edit_link(auth_client):
    html = auth_client.get(MANAGE_URL).content.decode()
    assert 'target="_blank"' not in html


@pytest.mark.django_db
def test_manager_offers_an_unused_only_toggle(auth_client):
    html = squash(auth_client.get(MANAGE_URL).content.decode())
    toggle = tag(html, "unused-only")
    assert 'name="unused"' in toggle
    assert 'type="checkbox"' in toggle
    # Not a bare "checked" check: the tag's hx-include names .ingredient-pick:checked.
    assert 'value="1" checked' not in toggle


@pytest.mark.django_db
def test_search_unused_only_hides_used_ingredients(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    make_ingredient("leftover")
    add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=onion)
    html = auth_client.get(SEARCH_URL, {"unused": "1"}).content.decode()
    assert "leftover" in html
    assert "onion" not in html
    assert "1 found / 0 selected" in html


@pytest.mark.django_db
def test_manager_keeps_the_unused_toggle_ticked(auth_client):
    html = squash(auth_client.get(MANAGE_URL, {"unused": "1"}).content.decode())
    assert 'value="1" checked' in tag(html, "unused-only")


@pytest.mark.django_db
def test_cancel_preserves_the_unused_filter(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    make_ingredient("leftover")
    add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=onion)
    html = auth_client.get(CANCEL_URL, {"unused": "1"}).content.decode()
    assert "leftover" in html
    assert "onion" not in html


@pytest.mark.django_db
def test_delete_leaves_the_unused_filter_applied(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    """Deleting orphans should leave you looking at the remaining orphans."""
    onion = make_ingredient("onion")
    doomed = make_ingredient("doomed")
    make_ingredient("leftover")
    add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=onion)
    html = auth_client.post(
        DELETE_URL, {"ingredient_ids": [doomed.pk], "unused": "1"}
    ).content.decode()
    assert "leftover" in html
    assert "onion" not in html
    assert "doomed" not in html


@pytest.mark.django_db
def test_selection_change_respects_the_unused_filter(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    leftover = make_ingredient("leftover")
    add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=onion)
    html = auth_client.get(
        RECIPES_URL, {"unused": "1", "ingredient_ids": [leftover.pk]}
    ).content.decode()
    assert "1 found / 1 selected" in html


@pytest.mark.django_db
def test_ingredient_column_sends_the_unused_toggle_with_its_refresh(auth_client):
    column = tag(squash(auth_client.get(SEARCH_URL).content.decode()), "col-ingredients")
    assert "#unused-only" in column


@pytest.mark.django_db
def test_header_checkbox_is_clear_when_nothing_is_selected(auth_client, make_ingredient):
    make_ingredient("onion")
    box = tag(squash(auth_client.get(SEARCH_URL).content.decode()), "select-all")
    assert not has_bare_attr(box, "checked")
    assert 'data-indeterminate="false"' in box


@pytest.mark.django_db
def test_header_checkbox_is_dashed_when_some_are_selected(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    make_ingredient("carrot")
    box = tag(
        squash(auth_client.get(SEARCH_URL, {"ingredient_ids": [onion.pk]}).content.decode()),
        "select-all",
    )
    assert not has_bare_attr(box, "checked")
    assert 'data-indeterminate="true"' in box


@pytest.mark.django_db
def test_header_checkbox_is_ticked_when_every_listed_row_is_selected(auth_client, make_ingredient):
    ids = [make_ingredient(name).pk for name in ("onion", "carrot")]
    box = tag(
        squash(auth_client.get(SEARCH_URL, {"ingredient_ids": ids}).content.decode()),
        "select-all",
    )
    assert has_bare_attr(box, "checked")
    assert 'data-indeterminate="false"' in box


@pytest.mark.django_db
def test_header_checkbox_ignores_selected_rows_the_filter_hides(auth_client, make_ingredient):
    """Filtering already narrows the selection, so only listed rows count."""
    onion = make_ingredient("onion")
    carrot = make_ingredient("carrot")
    box = tag(
        squash(
            auth_client.get(
                SEARCH_URL, {"q": "oni", "ingredient_ids": [onion.pk, carrot.pk]}
            ).content.decode()
        ),
        "select-all",
    )
    assert has_bare_attr(box, "checked")


@pytest.mark.django_db
def test_toggle_all_from_empty_selects_everything_listed(auth_client, make_ingredient):
    ids = [make_ingredient(name).pk for name in ("onion", "carrot", "aubergine")]
    html = squash(auth_client.get(SEARCH_URL, {"toggle_all": "1"}).content.decode())
    for ingredient_id in ids:
        assert f'value="{ingredient_id}" checked' in html
    assert "3 found / 3 selected" in html


@pytest.mark.django_db
def test_toggle_all_from_full_clears_the_selection(auth_client, make_ingredient):
    ids = [make_ingredient(name).pk for name in ("onion", "carrot")]
    html = squash(
        auth_client.get(SEARCH_URL, {"toggle_all": "1", "ingredient_ids": ids}).content.decode()
    )
    assert "2 found / 0 selected" in html
    assert "checked>" not in html.replace(" ", "")


@pytest.mark.django_db
def test_toggle_all_from_partial_selects_everything(auth_client, make_ingredient):
    onion = make_ingredient("onion")
    carrot = make_ingredient("carrot")
    html = squash(
        auth_client.get(
            SEARCH_URL, {"toggle_all": "1", "ingredient_ids": [onion.pk]}
        ).content.decode()
    )
    assert f'value="{carrot.pk}" checked' in html
    assert "2 found / 2 selected" in html


@pytest.mark.django_db
def test_toggle_all_only_takes_what_the_filters_leave(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    used = make_ingredient("onion")
    orphan = make_ingredient("leftover")
    add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=used)
    html = squash(auth_client.get(SEARCH_URL, {"unused": "1", "toggle_all": "1"}).content.decode())
    assert f'value="{orphan.pk}" checked' in html
    assert "1 found / 1 selected" in html


@pytest.mark.django_db
def test_toggle_all_refreshes_the_matches_and_the_actions(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    make_ingredient("carrot")
    add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=onion)
    html = squash(auth_client.get(SEARCH_URL, {"toggle_all": "1"}).content.decode())
    assert not has_bare_attr(tag(html, "action-merge"), "disabled")
    assert "1 matches / 2 selected" in html


@pytest.mark.django_db
def test_toggle_all_on_an_empty_list_selects_nothing(auth_client):
    html = squash(auth_client.get(SEARCH_URL, {"toggle_all": "1"}).content.decode())
    assert "0 found / 0 selected" in html
    assert not has_bare_attr(tag(html, "select-all"), "checked")
    assert 'data-indeterminate="false"' in tag(html, "select-all")


@pytest.mark.django_db
def test_matches_response_dashes_the_header_when_some_are_selected(auth_client, make_ingredient):
    """Ticking a row refreshes the header out of band — that is where the dash appears."""
    onion = make_ingredient("onion")
    make_ingredient("carrot")
    html = squash(auth_client.get(RECIPES_URL, {"ingredient_ids": [onion.pk]}).content.decode())
    box = tag(html, "select-all")
    assert 'data-indeterminate="true"' in box
    assert not has_bare_attr(box, "checked")


@pytest.mark.django_db
def test_selection_change_clears_a_stale_preview(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    """Column 4 must not keep showing a recipe the matches no longer contain."""
    onion = make_ingredient("onion")
    for name in ("Moussaka", "Ratatouille"):
        add_ingredient(recipe=make_recipe(owner=user, name=name), ingredient=onion)
    html = auth_client.get(RECIPES_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    preview = tag(html, "col-preview")
    assert 'hx-swap-oob="true"' in preview
    assert "preview-title" not in html.split('id="col-preview"')[1]


@pytest.mark.django_db
def test_a_single_match_loads_itself_into_the_preview(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    html = auth_client.get(RECIPES_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    pane = html.split('id="col-preview"')[1]
    assert "preview-title" in pane
    assert "Moussaka" in pane


@pytest.mark.django_db
def test_search_also_refreshes_the_preview(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    html = auth_client.get(SEARCH_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    preview = tag(html, "col-preview")
    assert 'hx-swap-oob="true"' in preview
    assert "Moussaka" in html.split('id="col-preview"')[1]


@pytest.mark.django_db
def test_full_page_previews_a_lone_match(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=onion)
    html = auth_client.get(MANAGE_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    assert "preview-title" in html.split('id="col-preview"')[1]


@pytest.mark.django_db
def test_cancel_previews_a_lone_match(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=onion)
    html = auth_client.get(CANCEL_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    assert "Moussaka" in html.split('id="col-preview"')[1]


@pytest.mark.django_db
def test_an_empty_selection_leaves_the_preview_empty(auth_client, make_ingredient):
    make_ingredient("onion")
    html = auth_client.get(RECIPES_URL).content.decode()
    assert "preview-title" not in html.split('id="col-preview"')[1]


@pytest.mark.django_db
def test_the_auto_preview_is_owner_scoped(
    auth_client, other_user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    add_ingredient(recipe=make_recipe(owner=other_user, name="Their Soup"), ingredient=onion)
    html = auth_client.get(RECIPES_URL, {"ingredient_ids": [onion.pk]}).content.decode()
    assert "Their Soup" not in html


@pytest.mark.django_db
def test_preview_pluralises_a_countable_ingredient(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    """The preview reads the same as the recipe page it mirrors (plan 009)."""
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion, quantity=Decimal("2"))
    html = squash(auth_client.get(preview_url(moussaka.pk)).content.decode())
    assert "2 onions" in html


@pytest.mark.django_db
def test_preview_keeps_the_singular_when_a_unit_is_given(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion, quantity=Decimal("200"), unit="g")
    html = squash(auth_client.get(preview_url(moussaka.pk)).content.decode())
    assert "200 g onion" in html
    assert "onions" not in html


@pytest.mark.django_db
def test_manager_offers_a_plurals_only_toggle(auth_client):
    html = squash(auth_client.get(MANAGE_URL).content.decode())
    toggle = tag(html, "plurals-only")
    assert 'name="plurals"' in toggle
    assert 'type="checkbox"' in toggle
    assert 'value="1" checked' not in toggle


@pytest.mark.django_db
def test_search_plurals_only_lists_both_halves_of_each_pair(auth_client, make_ingredient):
    """Finding `onion` next to `onions` is the first step of merging them away."""
    make_ingredient("onion")
    make_ingredient("onions")
    make_ingredient("carrot")
    html = auth_client.get(SEARCH_URL, {"plurals": "1"}).content.decode()
    assert "onion" in html
    assert "onions" in html
    assert "carrot" not in html
    assert "2 found / 0 selected" in html


@pytest.mark.django_db
def test_manager_keeps_the_plurals_toggle_ticked(auth_client):
    html = squash(auth_client.get(MANAGE_URL, {"plurals": "1"}).content.decode())
    assert 'value="1" checked' in tag(html, "plurals-only")


@pytest.mark.django_db
def test_cancel_preserves_the_plurals_filter(auth_client, make_ingredient):
    make_ingredient("onion")
    make_ingredient("onions")
    make_ingredient("carrot")
    html = auth_client.get(CANCEL_URL, {"plurals": "1"}).content.decode()
    assert "onions" in html
    assert "carrot" not in html


@pytest.mark.django_db
def test_merge_leaves_the_plurals_filter_applied(auth_client, make_ingredient):
    """Merging the plural away should leave you looking at the remaining pairs."""
    onion = make_ingredient("onion")
    onions = make_ingredient("onions")
    make_ingredient("tomato")
    make_ingredient("tomatoes")
    html = auth_client.post(
        MERGE_URL,
        {"ingredient_ids": [onion.pk, onions.pk], "survivor_id": onion.pk, "plurals": "1"},
    ).content.decode()
    # 2, not 3: the surviving `onion` has no plural partner left, so it drops
    # out of the filtered column along with the row it absorbed.
    assert "2 found / 1 selected" in html
    assert "tomatoes" in html
    assert "onions" not in html


@pytest.mark.django_db
def test_ingredient_column_sends_the_plurals_toggle_with_its_refresh(auth_client):
    column = tag(squash(auth_client.get(SEARCH_URL).content.decode()), "col-ingredients")
    assert "#plurals-only" in column


@pytest.mark.django_db
def test_edit_panel_offers_the_plural_name_override(auth_client, make_ingredient):
    avocado = make_ingredient("avocado")
    html = auth_client.get(EDIT_URL, {"ingredient_ids": [avocado.pk]}).content.decode()
    assert 'name="plural_name"' in html


@pytest.mark.django_db
def test_saving_a_plural_override_changes_what_the_recipe_page_shows(
    auth_client, user, make_ingredient, make_recipe, add_ingredient
):
    avocado = make_ingredient("avocado")
    recipe = make_recipe(owner=user, name="Guacamole")
    add_ingredient(recipe=recipe, ingredient=avocado, quantity=Decimal("3"))
    auth_client.post(
        save_url(avocado.pk), {"ingredient_name": "avocado", "plural_name": "avocados"}
    )
    html = auth_client.get(recipe.get_absolute_url()).content.decode()
    assert '<span class="ingredient-name">avocados</span>' in html
