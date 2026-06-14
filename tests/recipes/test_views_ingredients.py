"""Tests for recipe ingredient/group inline-edit views (Plan 004, Step 2)."""

import pytest
from django.test import Client

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe


@pytest.fixture
def auth_client(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def recipe(user, db):
    return Recipe.objects.create(recipe_name="Ingredient Recipe", owner=user)


@pytest.fixture
def group(recipe):
    return IngredientGroup.objects.create(recipe=recipe, group_name="Main", index_in_sequence=0)


@pytest.fixture
def iir(group):
    ing = Ingredient.objects.create(ingredient_name="onion")
    return IngredientInRecipe.objects.create(
        ingredient=ing,
        ingredient_group=group,
        index_in_sequence=0,
        quantity=2,
        unit="pcs",
        preparation="diced",
        note="",
    )


@pytest.mark.django_db
def test_ingredient_display_returns_200(auth_client, recipe, iir):
    response = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_ingredient_display_no_form_elements(auth_client, recipe, iir):
    response = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/")
    assert "<form" not in response.content.decode()


@pytest.mark.django_db
def test_ingredient_display_404_wrong_recipe(auth_client, user, iir, db):
    other = Recipe.objects.create(recipe_name="Other", owner=user)
    response = auth_client.get(f"/recipes/{other.pk}/ingredients/{iir.pk}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_ingredient_edit_returns_200(auth_client, recipe, iir):
    response = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/edit/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_ingredient_edit_has_form(auth_client, recipe, iir):
    response = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/edit/")
    assert "<form" in response.content.decode()


@pytest.mark.django_db
def test_ingredient_edit_cancel_button_points_to_display(auth_client, recipe, iir):
    response = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/edit/")
    display_url = f"/recipes/{recipe.pk}/ingredients/{iir.pk}/"
    assert display_url in response.content.decode()


@pytest.mark.django_db
def test_ingredient_save_post_valid_saves_and_returns_display(auth_client, recipe, iir):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/{iir.pk}/save/",
        {
            "ingredient_name": "onion",
            "quantity": "3.00",
            "unit": "kg",
            "preparation": "sliced",
            "note": "",
        },
    )
    assert response.status_code == 200
    iir.refresh_from_db()
    assert iir.unit == "kg"
    assert "<form" not in response.content.decode()


@pytest.mark.django_db
def test_ingredient_save_post_invalid_returns_form(auth_client, recipe, iir):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/{iir.pk}/save/",
        {"ingredient_name": "onion", "quantity": "-5", "unit": "kg", "preparation": "", "note": ""},
    )
    assert response.status_code == 200
    assert "<form" in response.content.decode()


@pytest.mark.django_db
def test_ingredient_delete_removes_iir(auth_client, recipe, iir):
    iir_id = iir.pk
    response = auth_client.post(f"/recipes/{recipe.pk}/ingredients/{iir_id}/delete/")
    assert response.status_code == 200
    assert not IngredientInRecipe.objects.filter(pk=iir_id).exists()


@pytest.mark.django_db
def test_ingredient_delete_reorders_remaining(auth_client, recipe, group):
    ing = Ingredient.objects.create(ingredient_name="garlic")
    ing2 = Ingredient.objects.create(ingredient_name="salt")
    i1 = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=0
    )
    i2 = IngredientInRecipe.objects.create(
        ingredient=ing2, ingredient_group=group, index_in_sequence=1
    )
    auth_client.post(f"/recipes/{recipe.pk}/ingredients/{i1.pk}/delete/")
    i2.refresh_from_db()
    assert i2.index_in_sequence == 0


@pytest.mark.django_db
def test_group_display_returns_200(auth_client, recipe, group):
    response = auth_client.get(f"/recipes/{recipe.pk}/groups/{group.pk}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_group_display_no_form_elements(auth_client, recipe, group):
    response = auth_client.get(f"/recipes/{recipe.pk}/groups/{group.pk}/")
    assert "<form" not in response.content.decode()


@pytest.mark.django_db
def test_group_edit_returns_200(auth_client, recipe, group):
    response = auth_client.get(f"/recipes/{recipe.pk}/groups/{group.pk}/edit/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_group_edit_has_form(auth_client, recipe, group):
    response = auth_client.get(f"/recipes/{recipe.pk}/groups/{group.pk}/edit/")
    assert "<form" in response.content.decode()


@pytest.mark.django_db
def test_group_save_post_valid_saves_and_returns_display(auth_client, recipe, group):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/groups/{group.pk}/save/",
        {"group_name": "Sauce"},
    )
    assert response.status_code == 200
    group.refresh_from_db()
    assert group.group_name == "Sauce"
    assert "<form" not in response.content.decode()


@pytest.mark.django_db
def test_group_save_blank_name_ok_when_only_group(auth_client, recipe, group):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/groups/{group.pk}/save/",
        {"group_name": ""},
    )
    assert response.status_code == 200
    assert "<form" not in response.content.decode()
    group.refresh_from_db()
    assert not group.group_name


@pytest.mark.django_db
def test_group_save_blank_name_rejected_when_multiple_groups(auth_client, recipe, group):
    IngredientGroup.objects.create(recipe=recipe, group_name="Second", index_in_sequence=1)
    response = auth_client.post(
        f"/recipes/{recipe.pk}/groups/{group.pk}/save/",
        {"group_name": ""},
    )
    assert response.status_code == 200
    assert "<form" in response.content.decode()
    group.refresh_from_db()
    assert group.group_name == "Main"  # unchanged


@pytest.mark.django_db
def test_group_display_shows_placeholder_when_no_name(auth_client, recipe):
    unnamed = IngredientGroup.objects.create(recipe=recipe, group_name="", index_in_sequence=0)
    response = auth_client.get(f"/recipes/{recipe.pk}/groups/{unnamed.pk}/")
    content = response.content.decode()
    assert "—" in content


@pytest.mark.django_db
def test_group_delete_removes_group(auth_client, recipe, group):
    group_id = group.pk
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/{group_id}/delete/")
    assert response.status_code == 200
    assert not IngredientGroup.objects.filter(pk=group_id).exists()


@pytest.mark.django_db
def test_group_add_does_not_create_group(auth_client, recipe):
    """Add only renders a blank form; the group is created on Save (create)."""
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/add/")
    assert response.status_code == 200
    assert IngredientGroup.objects.filter(recipe=recipe).count() == 0


@pytest.mark.django_db
def test_group_add_returns_edit_partial(auth_client, recipe):
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/add/")
    content = response.content.decode()
    assert "<form" in content
    assert f"/recipes/{recipe.pk}/groups/create/" in content


@pytest.mark.django_db
def test_group_create_valid_creates_group(auth_client, recipe):
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/create/", {"group_name": "Sauce"})
    assert response.status_code == 200
    group = IngredientGroup.objects.get(recipe=recipe)
    assert group.group_name == "Sauce"
    assert group.index_in_sequence == 0


@pytest.mark.django_db
def test_group_create_response_includes_ingredients_list_and_add_button(auth_client, recipe):
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/create/", {"group_name": "Sauce"})
    group = IngredientGroup.objects.get(recipe=recipe)
    content = response.content.decode()
    assert "ingredients-list" in content
    assert f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/add/" in content


@pytest.mark.django_db
def test_group_create_inserts_at_posted_position(auth_client, recipe, group):
    """Group draft saved with a position lands there; existing groups shift up."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/groups/create/", {"group_name": "Earlier", "position": "0"}
    )
    assert response.status_code == 200
    group.refresh_from_db()
    earlier = IngredientGroup.objects.get(recipe=recipe, group_name="Earlier")
    assert earlier.index_in_sequence == 0
    assert group.index_in_sequence == 1


@pytest.mark.django_db
def test_group_add_form_sends_position(auth_client, recipe):
    """Draft form carries the hx-on hook that posts its DOM position on save."""
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/add/")
    content = response.content.decode()
    assert "hx-on::config-request" in content
    assert "position" in content


@pytest.mark.django_db
def test_group_create_reverse_order_drafts_keep_dom_order(auth_client, recipe, group):
    """Two group drafts (DOM positions 1 and 2) saved in reverse order keep slots."""
    auth_client.post(
        f"/recipes/{recipe.pk}/groups/create/", {"group_name": "SecondDraft", "position": "2"}
    )
    auth_client.post(
        f"/recipes/{recipe.pk}/groups/create/", {"group_name": "FirstDraft", "position": "1"}
    )
    first = IngredientGroup.objects.get(recipe=recipe, group_name="FirstDraft")
    second = IngredientGroup.objects.get(recipe=recipe, group_name="SecondDraft")
    assert first.index_in_sequence == 1
    assert second.index_in_sequence == 2


@pytest.mark.django_db
def test_group_create_first_group_may_be_nameless(auth_client, recipe):
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/create/", {"group_name": ""})
    assert response.status_code == 200
    assert IngredientGroup.objects.filter(recipe=recipe).count() == 1


@pytest.mark.django_db
def test_group_create_second_group_requires_name(auth_client, recipe, group):
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/create/", {"group_name": ""})
    assert response.status_code == 200
    assert IngredientGroup.objects.filter(recipe=recipe).count() == 1  # only the fixture group
    assert "Group name required" in response.content.decode()


@pytest.fixture
def second_group(recipe):
    return IngredientGroup.objects.create(recipe=recipe, group_name="Second", index_in_sequence=1)


@pytest.mark.django_db
def test_ingredient_edit_shows_ingredient_name(auth_client, recipe, iir):
    response = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/edit/")
    assert "onion" in response.content.decode()


@pytest.mark.django_db
def test_ingredient_edit_shows_datalist_with_suggestions(auth_client, recipe, iir):
    Ingredient.objects.create(ingredient_name="garlic")
    response = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/edit/")
    content = response.content.decode()
    assert "<datalist" in content
    assert "garlic" in content
    assert "onion" in content


@pytest.mark.django_db
def test_ingredient_edit_field_order_quantity_unit_name(auth_client, recipe, iir):
    response = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/edit/")
    content = response.content.decode()
    qty_pos = content.index('name="quantity"')
    unit_pos = content.index('name="unit"')
    name_pos = content.index('name="ingredient_name"')
    assert qty_pos < unit_pos < name_pos


@pytest.mark.django_db
def test_ingredient_save_changes_ingredient_name(auth_client, recipe, iir):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/{iir.pk}/save/",
        {
            "ingredient_name": "garlic",
            "quantity": "2.00",
            "unit": "pcs",
            "preparation": "diced",
            "note": "",
        },
    )
    assert response.status_code == 200
    iir.refresh_from_db()
    assert iir.ingredient.ingredient_name == "garlic"


@pytest.mark.django_db
def test_ingredient_save_reuses_existing_ingredient(auth_client, recipe, iir):
    existing = Ingredient.objects.create(ingredient_name="garlic")
    auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/{iir.pk}/save/",
        {
            "ingredient_name": "garlic",
            "quantity": "2.00",
            "unit": "pcs",
            "preparation": "",
            "note": "",
        },
    )
    iir.refresh_from_db()
    assert iir.ingredient == existing
    assert Ingredient.objects.filter(ingredient_name="garlic").count() == 1


@pytest.mark.django_db
def test_ingredient_add_does_not_create_row(auth_client, recipe, group):
    """Add only renders a blank form; the row is created on Save (create)."""
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/add/")
    assert response.status_code == 200
    assert IngredientInRecipe.objects.filter(ingredient_group=group).count() == 0
    content = response.content.decode()
    assert "<form" in content
    assert f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/create/" in content


@pytest.mark.django_db
def test_ingredient_create_targets_specified_group(auth_client, recipe, group, second_group):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/groups/{second_group.pk}/ingredients/create/",
        {"ingredient_name": "carrot", "quantity": "1", "unit": "", "preparation": "", "note": ""},
    )
    assert response.status_code == 200
    assert IngredientInRecipe.objects.filter(ingredient_group=second_group).count() == 1
    assert IngredientInRecipe.objects.filter(ingredient_group=group).count() == 0


@pytest.mark.django_db
def test_ingredient_create_valid_returns_display(auth_client, recipe, group):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/create/",
        {
            "ingredient_name": "carrot",
            "quantity": "2",
            "unit": "pcs",
            "preparation": "",
            "note": "",
        },
    )
    assert response.status_code == 200
    iir = IngredientInRecipe.objects.get(ingredient_group=group)
    assert iir.ingredient.ingredient_name == "carrot"
    assert iir.index_in_sequence == 0
    assert "carrot" in response.content.decode()


@pytest.mark.django_db
def test_ingredient_create_inserts_at_posted_position(auth_client, recipe, group, iir):
    """Draft saved with a position lands there; existing rows shift up."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/create/",
        {
            "ingredient_name": "carrot",
            "quantity": "",
            "unit": "",
            "preparation": "",
            "note": "",
            "position": "0",
        },
    )
    assert response.status_code == 200
    iir.refresh_from_db()
    carrot = IngredientInRecipe.objects.get(
        ingredient_group=group, ingredient__ingredient_name="carrot"
    )
    assert carrot.index_in_sequence == 0
    assert iir.index_in_sequence == 1


@pytest.mark.django_db
def test_ingredient_add_form_sends_position(auth_client, recipe, group):
    """Draft form carries the hx-on hook that posts its DOM position on save."""
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/add/")
    content = response.content.decode()
    assert "hx-on::config-request" in content
    assert "position" in content


@pytest.mark.django_db
def test_ingredient_create_reverse_order_drafts_keep_dom_order(auth_client, recipe, group, iir):
    """Two drafts (DOM positions 1 and 2) saved in reverse order keep their slots."""
    auth_client.post(
        f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/create/",
        {
            "ingredient_name": "second-draft",
            "quantity": "",
            "unit": "",
            "preparation": "",
            "note": "",
            "position": "2",
        },
    )
    auth_client.post(
        f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/create/",
        {
            "ingredient_name": "first-draft",
            "quantity": "",
            "unit": "",
            "preparation": "",
            "note": "",
            "position": "1",
        },
    )
    first = IngredientInRecipe.objects.get(ingredient__ingredient_name="first-draft")
    second = IngredientInRecipe.objects.get(ingredient__ingredient_name="second-draft")
    assert first.index_in_sequence == 1
    assert second.index_in_sequence == 2


@pytest.mark.django_db
def test_ingredient_create_invalid_creates_nothing_returns_form(auth_client, recipe, group):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/create/",
        {"ingredient_name": "", "quantity": "", "unit": "", "preparation": "", "note": ""},
    )
    assert response.status_code == 200
    assert IngredientInRecipe.objects.filter(ingredient_group=group).count() == 0
    assert Ingredient.objects.count() == 0
    assert "<form" in response.content.decode()


@pytest.mark.django_db
def test_ingredient_display_comma_when_both_name_and_preparation(auth_client, recipe, group):
    ing = Ingredient.objects.create(ingredient_name="onion")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing,
        ingredient_group=group,
        index_in_sequence=0,
        preparation="diced",
    )
    response = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/")
    content = response.content.decode()
    name_pos = content.index("ingredient-name")
    comma_pos = content.index(",", name_pos)
    prep_pos = content.index("ingredient-preparation", name_pos)
    assert name_pos < comma_pos < prep_pos


@pytest.mark.django_db
def test_ingredient_display_no_comma_when_preparation_empty(auth_client, recipe, group):
    ing = Ingredient.objects.create(ingredient_name="onion")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing,
        ingredient_group=group,
        index_in_sequence=0,
        preparation="",
    )
    response = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/")
    content = response.content.decode()
    name_pos = content.index("ingredient-name")
    prep_pos = content.index("ingredient-preparation", name_pos)
    assert "," not in content[name_pos:prep_pos]


@pytest.mark.django_db
def test_ingredient_display_shows_note_in_parentheses(auth_client, recipe, group):
    ing = Ingredient.objects.create(ingredient_name="onion")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing,
        ingredient_group=group,
        index_in_sequence=0,
        note="from the garden",
    )
    response = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/")
    content = response.content.decode()
    assert "(from the garden)" in content


@pytest.mark.django_db
def test_ingredient_display_note_after_preparation(auth_client, recipe, group):
    ing = Ingredient.objects.create(ingredient_name="onion")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing,
        ingredient_group=group,
        index_in_sequence=0,
        preparation="diced",
        note="from the garden",
    )
    response = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/")
    content = response.content.decode()
    prep_pos = content.index("ingredient-preparation")
    note_pos = content.index("(from the garden)")
    assert prep_pos < note_pos


@pytest.mark.django_db
def test_ingredient_display_no_note_when_empty(auth_client, recipe, group):
    ing = Ingredient.objects.create(ingredient_name="onion")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing,
        ingredient_group=group,
        index_in_sequence=0,
        note="",
    )
    response = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/")
    content = response.content.decode()
    assert "ingredient-note" not in content


@pytest.mark.django_db
def test_ingredient_create_with_gap_in_sequence_no_integrity_error(auth_client, recipe, group):
    """count()-based next index collides when a gap exists; Max+1 does not."""
    ing1 = Ingredient.objects.create(ingredient_name="garlic")
    ing2 = Ingredient.objects.create(ingredient_name="salt")
    # Manually create a gap: item at index 1 only (index 0 missing), count=1, max=1
    IngredientInRecipe.objects.create(ingredient=ing1, ingredient_group=group, index_in_sequence=1)
    IngredientInRecipe.objects.create(ingredient=ing2, ingredient_group=group, index_in_sequence=3)
    # count=2, max=3 → count-based next=2 (no collision here, but max-based=4)
    # Simpler: count=1, existing item at index 1 → count-based next=1 = collision
    IngredientInRecipe.objects.filter(ingredient=ing2).delete()
    # Now: count=1, one item at index 1 → count-based next=1 → IntegrityError
    response = auth_client.post(
        f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/create/",
        {"ingredient_name": "pepper", "quantity": "", "unit": "", "preparation": "", "note": ""},
    )
    assert response.status_code == 200
    assert IngredientInRecipe.objects.filter(ingredient_group=group).count() == 2


@pytest.fixture
def three_groups(recipe):
    g0 = IngredientGroup.objects.create(recipe=recipe, group_name="A", index_in_sequence=0)
    g1 = IngredientGroup.objects.create(recipe=recipe, group_name="B", index_in_sequence=1)
    g2 = IngredientGroup.objects.create(recipe=recipe, group_name="C", index_in_sequence=2)
    return g0, g1, g2


@pytest.fixture
def three_iirs(group):
    ing0 = Ingredient.objects.create(ingredient_name="alpha")
    ing1 = Ingredient.objects.create(ingredient_name="beta")
    ing2 = Ingredient.objects.create(ingredient_name="gamma")
    i0 = IngredientInRecipe.objects.create(
        ingredient=ing0, ingredient_group=group, index_in_sequence=0
    )
    i1 = IngredientInRecipe.objects.create(
        ingredient=ing1, ingredient_group=group, index_in_sequence=1
    )
    i2 = IngredientInRecipe.objects.create(
        ingredient=ing2, ingredient_group=group, index_in_sequence=2
    )
    return i0, i1, i2


@pytest.mark.django_db
def test_group_move_up_swaps_indexes(auth_client, recipe, three_groups):
    g0, g1, _ = three_groups
    auth_client.post(f"/recipes/{recipe.pk}/groups/{g1.pk}/move-up/")
    g0.refresh_from_db()
    g1.refresh_from_db()
    assert g1.index_in_sequence == 0
    assert g0.index_in_sequence == 1


@pytest.mark.django_db
def test_group_move_down_swaps_indexes(auth_client, recipe, three_groups):
    g0, g1, _ = three_groups
    auth_client.post(f"/recipes/{recipe.pk}/groups/{g0.pk}/move-down/")
    g0.refresh_from_db()
    g1.refresh_from_db()
    assert g0.index_in_sequence == 1
    assert g1.index_in_sequence == 0


@pytest.mark.django_db
def test_group_move_up_at_first_is_noop(auth_client, recipe, three_groups):
    g0, _, _ = three_groups
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/{g0.pk}/move-up/")
    assert response.status_code == 200
    g0.refresh_from_db()
    assert g0.index_in_sequence == 0


@pytest.mark.django_db
def test_group_move_down_at_last_is_noop(auth_client, recipe, three_groups):
    _, _, g2 = three_groups
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/{g2.pk}/move-down/")
    assert response.status_code == 200
    g2.refresh_from_db()
    assert g2.index_in_sequence == 2


@pytest.mark.django_db
def test_group_move_returns_groups_list(auth_client, recipe, three_groups):
    _, g1, _ = three_groups
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/{g1.pk}/move-up/")
    content = response.content.decode()
    assert "A" in content
    assert "B" in content
    assert "C" in content


@pytest.mark.django_db
def test_ingredient_move_up_swaps_indexes(auth_client, recipe, group, three_iirs):
    i0, i1, _ = three_iirs
    auth_client.post(f"/recipes/{recipe.pk}/ingredients/{i1.pk}/move-up/")
    i0.refresh_from_db()
    i1.refresh_from_db()
    assert i1.index_in_sequence == 0
    assert i0.index_in_sequence == 1


@pytest.mark.django_db
def test_ingredient_move_down_swaps_indexes(auth_client, recipe, group, three_iirs):
    i0, i1, _ = three_iirs
    auth_client.post(f"/recipes/{recipe.pk}/ingredients/{i0.pk}/move-down/")
    i0.refresh_from_db()
    i1.refresh_from_db()
    assert i0.index_in_sequence == 1
    assert i1.index_in_sequence == 0


@pytest.mark.django_db
def test_ingredient_move_up_at_first_is_noop(auth_client, recipe, group, three_iirs):
    i0, _, _ = three_iirs
    response = auth_client.post(f"/recipes/{recipe.pk}/ingredients/{i0.pk}/move-up/")
    assert response.status_code == 200
    i0.refresh_from_db()
    assert i0.index_in_sequence == 0


@pytest.mark.django_db
def test_ingredient_move_down_at_last_is_noop(auth_client, recipe, group, three_iirs):
    _, _, i2 = three_iirs
    response = auth_client.post(f"/recipes/{recipe.pk}/ingredients/{i2.pk}/move-down/")
    assert response.status_code == 200
    i2.refresh_from_db()
    assert i2.index_in_sequence == 2


@pytest.mark.django_db
def test_ingredient_move_returns_iir_list(auth_client, recipe, group, three_iirs):
    _, i1, _ = three_iirs
    response = auth_client.post(f"/recipes/{recipe.pk}/ingredients/{i1.pk}/move-up/")
    content = response.content.decode()
    assert "alpha" in content
    assert "beta" in content
    assert "gamma" in content


# --- ingredient reassign ---


@pytest.fixture
def group2(recipe):
    return IngredientGroup.objects.create(recipe=recipe, group_name="Sauce", index_in_sequence=1)


@pytest.fixture
def iir2(group):
    ing = Ingredient.objects.create(ingredient_name="garlic")
    return IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=1
    )


@pytest.mark.django_db
def test_ingredient_reassign_moves_to_existing_group(auth_client, recipe, group, group2, iir, iir2):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [iir.pk, iir2.pk], "target_group": group2.pk},
    )
    assert response.status_code == 200
    iir.refresh_from_db()
    iir2.refresh_from_db()
    assert iir.ingredient_group_id == group2.pk
    assert iir2.ingredient_group_id == group2.pk


@pytest.mark.django_db
def test_ingredient_reassign_creates_new_group(auth_client, recipe, group, iir, iir2):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [iir.pk, iir2.pk], "target_group": "new", "new_group_name": "Side"},
    )
    assert response.status_code == 200
    new_group = IngredientGroup.objects.get(recipe=recipe, group_name="Side")
    iir.refresh_from_db()
    assert iir.ingredient_group_id == new_group.pk


@pytest.mark.django_db
def test_ingredient_reassign_new_group_requires_name(auth_client, recipe, group, iir, iir2):
    """target_group=new with a blank name must not create a nameless group."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [iir.pk, iir2.pk], "target_group": "new", "new_group_name": ""},
    )
    assert response.status_code == 422
    assert "form-error" in response.content.decode()
    assert IngredientGroup.objects.filter(recipe=recipe).count() == 1
    iir.refresh_from_db()
    assert iir.ingredient_group == group


@pytest.mark.django_db
def test_ingredient_reassign_same_group_is_noop(auth_client, recipe, group, iir, iir2):
    """Reassigning a subset to its own group must not reorder anything."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [iir.pk], "target_group": group.pk},
    )
    assert response.status_code == 200
    iir.refresh_from_db()
    iir2.refresh_from_db()
    assert iir.index_in_sequence == 0
    assert iir2.index_in_sequence == 1


@pytest.mark.django_db
def test_ingredient_reassign_preserves_visual_order_across_groups(
    auth_client, recipe, group, group2, iir, iir2
):
    """Moved rows keep top-to-bottom page order (group order, then row order),
    not raw index order interleaved across source groups."""
    ing = Ingredient.objects.create(ingredient_name="cumin")
    iir3 = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group2, index_in_sequence=0
    )
    # Page order: iir2 (first group, idx 1) above iir3 (second group, idx 0)
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [iir3.pk, iir2.pk], "target_group": group2.pk},
    )
    assert response.status_code == 200
    iir2.refresh_from_db()
    iir3.refresh_from_db()
    assert iir2.index_in_sequence == 0
    assert iir3.index_in_sequence == 1


@pytest.mark.django_db
def test_ingredient_reassign_interleaves_by_page_order_when_target_has_existing_rows(
    auth_client, recipe, group, group2, iir, iir2, db
):
    """Moving iir (group idx=0, row idx=0) into group2 (idx=1) that already has
    existing_target (idx=0) must place iir BEFORE existing_target because iir's
    original page position is earlier, not append it at the end."""
    ing = Ingredient.objects.create(ingredient_name="basil")
    existing_target = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group2, index_in_sequence=0
    )
    auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [iir.pk], "target_group": group2.pk},
    )
    iir.refresh_from_db()
    existing_target.refresh_from_db()
    # iir was in group (index_in_sequence=0), existing_target is in group2 (index=1)
    # page order: iir comes first
    assert iir.index_in_sequence == 0
    assert existing_target.index_in_sequence == 1


@pytest.mark.django_db
def test_ingredient_reassign_reindexes_source_group(auth_client, recipe, group, group2, iir, iir2):
    ing3 = Ingredient.objects.create(ingredient_name="salt")
    iir3 = IngredientInRecipe.objects.create(
        ingredient=ing3, ingredient_group=group, index_in_sequence=2
    )
    auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [iir.pk], "target_group": group2.pk},
    )
    iir2.refresh_from_db()
    iir3.refresh_from_db()
    assert iir2.index_in_sequence == 0
    assert iir3.index_in_sequence == 1


@pytest.mark.django_db
def test_ingredient_reassign_same_group_no_integrity_error(auth_client, recipe, group, iir, iir2):
    """Moving to same group must not raise IntegrityError."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [iir.pk], "target_group": group.pk},
    )
    assert response.status_code == 200
    iir.refresh_from_db()
    assert iir.ingredient_group_id == group.pk


@pytest.mark.django_db
def test_ingredient_reassign_empty_ids_is_noop(auth_client, recipe, group, iir):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [], "target_group": group.pk},
    )
    assert response.status_code == 200
    iir.refresh_from_db()
    assert iir.ingredient_group_id == group.pk


@pytest.mark.django_db
def test_ingredient_reassign_all_foreign_ids_new_group_does_not_create_group(
    auth_client, recipe, user, group, iir, db
):
    """All posted IDs belong to another recipe; iirs is empty after filtering.
    target_group=new must not create an orphan empty group."""
    other_recipe = Recipe.objects.create(recipe_name="Other", owner=user)
    other_group = IngredientGroup.objects.create(
        recipe=other_recipe, group_name="X", index_in_sequence=0
    )
    ing = Ingredient.objects.create(ingredient_name="pepper")
    other_iir = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=other_group, index_in_sequence=0
    )
    before = IngredientGroup.objects.filter(recipe=recipe).count()
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [other_iir.pk], "target_group": "new", "new_group_name": "Ghost"},
    )
    assert response.status_code == 200
    assert IngredientGroup.objects.filter(recipe=recipe).count() == before


@pytest.mark.django_db
def test_ingredient_reassign_ignores_foreign_recipe_ids(
    auth_client, recipe, user, group, group2, iir, db
):
    other_recipe = Recipe.objects.create(recipe_name="Other", owner=user)
    other_group = IngredientGroup.objects.create(
        recipe=other_recipe, group_name="X", index_in_sequence=0
    )
    ing = Ingredient.objects.create(ingredient_name="pepper")
    other_iir = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=other_group, index_in_sequence=0
    )
    auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [iir.pk, other_iir.pk], "target_group": group2.pk},
    )
    other_iir.refresh_from_db()
    assert other_iir.ingredient_group_id == other_group.pk


@pytest.mark.django_db
def test_ingredient_reassign_returns_groups_list(auth_client, recipe, group, group2, iir, iir2):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [iir.pk, iir2.pk], "target_group": group2.pk},
    )
    content = response.content.decode()
    assert "reassign-panel" in content
    assert "ingredient_save" not in content


@pytest.mark.django_db
def test_ingredient_edit_partial_has_is_editing_class(auth_client, recipe, group, iir):
    """Edit template must render is-editing class so CSS can block move buttons."""
    response = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/edit/")
    assert "is-editing" in response.content.decode()


@pytest.mark.django_db
def test_group_edit_partial_has_is_editing_class(auth_client, recipe, group):
    """Edit template must render is-editing class so CSS can block move buttons."""
    response = auth_client.get(f"/recipes/{recipe.pk}/groups/{group.pk}/edit/")
    assert "is-editing" in response.content.decode()


# --- reassign dropdown OOB sync ---


@pytest.mark.django_db
def test_group_save_response_includes_reassign_dropdown_oob(auth_client, recipe, group):
    """Group rename must include OOB update for reassign <select> with new name."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/groups/{group.pk}/save/",
        {"group_name": "Sauce"},
    )
    content = response.content.decode()
    assert "hx-swap-oob" in content
    assert "Sauce" in content
    assert "reassign-target" in content


@pytest.mark.django_db
def test_group_create_response_includes_reassign_dropdown_oob(auth_client, recipe):
    """New group creation must include OOB update so it appears in reassign dropdown."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/groups/create/",
        {"group_name": "New Group"},
    )
    content = response.content.decode()
    assert "hx-swap-oob" in content
    assert "New Group" in content
    assert "reassign-target" in content


@pytest.mark.django_db
def test_group_delete_response_includes_reassign_dropdown_oob(auth_client, recipe, group):
    """Group deletion must include OOB update so deleted group is removed from reassign dropdown."""
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/{group.pk}/delete/")
    content = response.content.decode()
    assert "hx-swap-oob" in content
    assert "reassign-target" in content
    assert "Main" not in content


@pytest.mark.django_db
def test_ingredient_reassign_non_numeric_group_id_returns_422(auth_client, recipe, group, iir):
    """Non-numeric target_group must be caught and return 422, not 500 from ValueError."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [iir.pk], "target_group": "notanumber"},
    )
    assert response.status_code == 422


@pytest.mark.django_db
def test_ingredient_reassign_empty_group_id_returns_422(auth_client, recipe, group, iir):
    """Empty target_group must be caught and return 422, not 500 from ValueError."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [iir.pk], "target_group": ""},
    )
    assert response.status_code == 422


@pytest.mark.django_db
def test_ingredient_reassign_deleted_group_returns_422(auth_client, recipe, group, iir):
    """Valid int target_group that no longer exists (deleted in another tab) must return 422."""
    deleted_id = group.pk
    group.delete()
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": [iir.pk], "target_group": str(deleted_id)},
    )
    assert response.status_code == 422


@pytest.mark.django_db
def test_ingredient_reassign_non_integer_ids_returns_422(auth_client, recipe, group, iir):
    """Tampered ingredient_ids with non-integer values must return 422, not 500."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/reassign/",
        {"ingredient_ids": ["abc", "not-an-int"], "target_group": str(group.pk)},
    )
    assert response.status_code == 422


@pytest.mark.django_db
def test_ingredient_reassign_new_group_acquires_recipe_lock(auth_client, recipe, group, iir):
    """reassign target_group=new must lock the recipe row before computing next index."""
    from unittest.mock import patch

    locked_models = []

    original_sfu = recipe.__class__.objects.none().__class__.select_for_update

    def spy_sfu(self, *args, **kwargs):
        locked_models.append(self.model.__name__)
        return original_sfu(self, *args, **kwargs)

    with patch("django.db.models.QuerySet.select_for_update", spy_sfu):
        auth_client.post(
            f"/recipes/{recipe.pk}/ingredients/reassign/",
            {
                "ingredient_ids": [iir.pk],
                "target_group": "new",
                "new_group_name": "New Group",
            },
        )
    assert "Recipe" in locked_models


@pytest.mark.django_db
def test_ingredient_create_no_orphan_ingredient_on_insert_failure(auth_client, recipe, group):
    """If insert_at_index raises after get_or_create, Ingredient row must be rolled back."""
    from unittest.mock import patch

    from django.db import IntegrityError

    from recipes.models import Ingredient

    with patch("recipes.views.recipe_ingredients.insert_at_index", side_effect=IntegrityError("seq")):
        with pytest.raises(IntegrityError):
            auth_client.post(
                f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/create/",
                {"ingredient_name": "orphan-veggie", "quantity": "", "unit": "", "preparation": "", "note": ""},
            )
    assert not Ingredient.objects.filter(ingredient_name="orphan-veggie").exists()


@pytest.mark.django_db
def test_group_create_blank_name_rejected_when_race_creates_sibling(auth_client, recipe):
    """Simulated race: competing blank group injected at parent-lock moment must be rejected."""
    from unittest.mock import patch

    from django.db.models.query import QuerySet

    original_sfu = QuerySet.select_for_update

    def inject_at_parent_lock(qs, *args, **kwargs):
        if qs.model is Recipe and not IngredientGroup.objects.filter(recipe=recipe).exists():
            IngredientGroup.objects.create(recipe=recipe, group_name="", index_in_sequence=0)
        return original_sfu(qs, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", inject_at_parent_lock):
        auth_client.post(f"/recipes/{recipe.pk}/groups/create/", {"group_name": ""})

    # Only the injected competitor should exist; this request must not create a second blank group
    assert IngredientGroup.objects.filter(recipe=recipe).count() == 1


@pytest.mark.django_db
def test_reassign_new_group_blank_name_race_rejected(auth_client, recipe, group):
    """Stale pre-lock count=0 would allow blank name; re-read count under lock=1 must reject it."""
    from unittest.mock import patch

    from django.db.models.query import QuerySet

    ing = Ingredient.objects.create(ingredient_name="pepper")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=0
    )

    locked = [False]
    original_sfu = QuerySet.select_for_update
    original_count = QuerySet.count

    def mock_lock(qs, *args, **kwargs):
        if qs.model is Recipe:
            locked[0] = True
        return original_sfu(qs, *args, **kwargs)

    def mock_count(qs):
        if qs.model is IngredientGroup and not locked[0]:
            return 0  # Simulate stale pre-lock read (race: another request saw 0 groups)
        return original_count(qs)

    with patch.object(QuerySet, "select_for_update", mock_lock):
        with patch.object(QuerySet, "count", mock_count):
            auth_client.post(
                f"/recipes/{recipe.pk}/ingredients/reassign/",
                {
                    "ingredient_ids": [iir.pk],
                    "target_group": "new",
                    "new_group_name": "",
                },
            )

    # Blank group must not be created; stale pre-lock count must not have allowed it
    assert IngredientGroup.objects.filter(recipe=recipe, group_name="").count() == 0


@pytest.mark.django_db
def test_reassign_existing_target_deleted_before_transaction_returns_422(auth_client, recipe, group):
    """Target group deleted concurrently must be caught inside the transaction via re-fetch."""
    from unittest.mock import patch

    from django.db.models.query import QuerySet

    target = IngredientGroup.objects.create(recipe=recipe, group_name="Target", index_in_sequence=1)
    ing = Ingredient.objects.create(ingredient_name="salt")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=0
    )

    original_sfu = QuerySet.select_for_update

    def delete_target_at_recipe_lock(qs, *args, **kwargs):
        # Simulate concurrent deletion of target group when Recipe lock is acquired
        if qs.model is Recipe:
            IngredientGroup.objects.filter(pk=target.pk).delete()
        return original_sfu(qs, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", delete_target_at_recipe_lock):
        response = auth_client.post(
            f"/recipes/{recipe.pk}/ingredients/reassign/",
            {"ingredient_ids": [iir.pk], "target_group": str(target.pk)},
        )

    assert response.status_code == 422
    # Ingredient must not have moved
    iir.refresh_from_db()
    assert iir.ingredient_group_id == group.pk


@pytest.mark.django_db
def test_reassign_does_not_overwrite_concurrent_quantity_edit(auth_client, recipe, group, second_group):
    """Re-fetch iirs inside transaction; only ingredient_group/index_in_sequence must be written."""
    from decimal import Decimal
    from unittest.mock import patch

    from django.db.models.query import QuerySet

    ing = Ingredient.objects.create(ingredient_name="salt")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=0, quantity=Decimal("5.00")
    )

    original_sfu = QuerySet.select_for_update

    def edit_qty_at_iir_lock(qs, *args, **kwargs):
        if qs.model is IngredientInRecipe:
            IngredientInRecipe.objects.filter(pk=iir.pk).update(quantity=Decimal("99.00"))
        return original_sfu(qs, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", edit_qty_at_iir_lock):
        auth_client.post(
            f"/recipes/{recipe.pk}/ingredients/reassign/",
            {"ingredient_ids": [iir.pk], "target_group": str(second_group.pk)},
        )

    iir.refresh_from_db()
    assert iir.ingredient_group == second_group
    assert iir.quantity == Decimal("99.00")  # must not revert to 5.00


@pytest.mark.django_db
def test_group_save_blank_name_rejected_when_concurrent_group_created(auth_client, recipe, group):
    """recipe_group_save must check group count under recipe lock.

    Lock Recipe first; inject concurrent group at lock time so count() returns 2;
    blank name must then be rejected. Without the lock the count runs before
    injection and returns 1, letting blank name through (the bug).
    """
    from unittest.mock import patch

    from django.db.models import QuerySet

    original_sfu = QuerySet.select_for_update

    def inject_at_recipe_lock(qs, *args, **kwargs):
        if qs.model is Recipe:
            IngredientGroup.objects.create(
                recipe=recipe, group_name="Concurrent", index_in_sequence=99
            )
        return original_sfu(qs, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", inject_at_recipe_lock):
        response = auth_client.post(
            f"/recipes/{recipe.pk}/groups/{group.pk}/save/",
            {"group_name": ""},
        )

    assert "Group name required" in response.content.decode()
    group.refresh_from_db()
    assert group.group_name == "Main"  # not overwritten with blank


@pytest.mark.django_db
def test_ingredient_delete_concurrent_reassign_still_deletes(auth_client, recipe, group, second_group):
    """Delete must proceed even if IIR was reassigned concurrently before the lock."""
    from unittest.mock import patch

    from django.db.models import QuerySet

    ing = Ingredient.objects.create(ingredient_name="coriander")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=0
    )

    original_sfu = QuerySet.select_for_update
    reassigned = []

    def reassign_at_iir_lock(qs, *args, **kwargs):
        if qs.model is IngredientInRecipe and not reassigned:
            reassigned.append(True)
            IngredientInRecipe.objects.filter(pk=iir.pk).update(
                ingredient_group=second_group, index_in_sequence=0
            )
        return original_sfu(qs, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", reassign_at_iir_lock):
        auth_client.post(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/delete/")

    assert not IngredientInRecipe.objects.filter(pk=iir.pk).exists()


@pytest.mark.django_db
def test_ingredient_move_up_concurrent_reassign_moves_in_fresh_group(
    auth_client, recipe, group, second_group
):
    """After concurrent reassign, move-up must operate in the IIR's fresh group."""
    from unittest.mock import patch

    from django.db.models import QuerySet

    ing0 = Ingredient.objects.create(ingredient_name="cumin-0")
    ing1 = Ingredient.objects.create(ingredient_name="cumin-1")
    ing2 = Ingredient.objects.create(ingredient_name="cumin-2")
    IngredientInRecipe.objects.create(
        ingredient=ing0, ingredient_group=group, index_in_sequence=0
    )
    iir_b = IngredientInRecipe.objects.create(
        ingredient=ing1, ingredient_group=group, index_in_sequence=1
    )
    iir_c = IngredientInRecipe.objects.create(
        ingredient=ing2, ingredient_group=second_group, index_in_sequence=0
    )

    original_sfu = QuerySet.select_for_update
    reassigned = []

    def reassign_at_iir_lock(qs, *args, **kwargs):
        if qs.model is IngredientInRecipe and not reassigned:
            reassigned.append(True)
            IngredientInRecipe.objects.filter(pk=iir_b.pk).update(
                ingredient_group=second_group, index_in_sequence=1
            )
        return original_sfu(qs, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", reassign_at_iir_lock):
        auth_client.post(f"/recipes/{recipe.pk}/ingredients/{iir_b.pk}/move-up/")

    iir_b.refresh_from_db()
    iir_c.refresh_from_db()
    # With fix: iir_b moves up within second_group, swapping with iir_c
    assert iir_b.index_in_sequence == 0
    assert iir_c.index_in_sequence == 1


@pytest.mark.django_db
def test_ingredient_create_group_deleted_concurrently_returns_error(auth_client, recipe, group):
    """Create must abort cleanly (404) if group is deleted before the lock is acquired."""
    from unittest.mock import patch

    from django.db.models import QuerySet

    original_sfu = QuerySet.select_for_update
    deleted = []

    def delete_group_at_lock(qs, *args, **kwargs):
        if qs.model is IngredientGroup and not deleted:
            deleted.append(True)
            IngredientGroup.objects.filter(pk=group.pk).delete()
        return original_sfu(qs, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", delete_group_at_lock):
        response = auth_client.post(
            f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/create/",
            {"ingredient_name": "turmeric", "quantity": "1", "unit": "tsp", "preparation": ""},
        )

    assert response.status_code == 404
    assert not IngredientInRecipe.objects.filter(
        ingredient__ingredient_name="turmeric"
    ).exists()


@pytest.mark.django_db
def test_group_save_group_deleted_concurrently_does_not_recreate(auth_client, recipe, group):
    """group_save must abort if group is deleted after get_object_or_404 and before save."""
    from unittest.mock import patch

    from django.db.models import QuerySet

    original_sfu = QuerySet.select_for_update
    deleted = []

    def delete_group_at_recipe_lock(qs, *args, **kwargs):
        if qs.model is Recipe and not deleted:
            deleted.append(True)
            IngredientGroup.objects.filter(pk=group.pk).delete()
        return original_sfu(qs, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", delete_group_at_recipe_lock):
        response = auth_client.post(
            f"/recipes/{recipe.pk}/groups/{group.pk}/save/",
            {"group_name": "Updated Name"},
        )

    assert response.status_code == 404
    assert not IngredientGroup.objects.filter(pk=group.pk).exists()
