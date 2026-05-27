"""Tests for recipe ingredient/group inline-edit views (Plan 004, Step 2)."""

import pytest
from django.test import Client

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe


@pytest.fixture
def client():
    return Client()


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
def test_ingredient_display_returns_200(client, recipe, iir):
    response = client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_ingredient_display_no_form_elements(client, recipe, iir):
    response = client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/")
    assert "<form" not in response.content.decode()


@pytest.mark.django_db
def test_ingredient_display_404_wrong_recipe(client, user, iir, db):
    other = Recipe.objects.create(recipe_name="Other", owner=user)
    response = client.get(f"/recipes/{other.pk}/ingredients/{iir.pk}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_ingredient_edit_returns_200(client, recipe, iir):
    response = client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/edit/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_ingredient_edit_has_form(client, recipe, iir):
    response = client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/edit/")
    assert "<form" in response.content.decode()


@pytest.mark.django_db
def test_ingredient_edit_cancel_button_points_to_display(client, recipe, iir):
    response = client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/edit/")
    display_url = f"/recipes/{recipe.pk}/ingredients/{iir.pk}/"
    assert display_url in response.content.decode()


@pytest.mark.django_db
def test_ingredient_save_post_valid_saves_and_returns_display(client, recipe, iir):
    response = client.post(
        f"/recipes/{recipe.pk}/ingredients/{iir.pk}/save/",
        {"quantity": "3.00", "unit": "kg", "preparation": "sliced", "note": ""},
    )
    assert response.status_code == 200
    iir.refresh_from_db()
    assert iir.unit == "kg"
    assert "<form" not in response.content.decode()


@pytest.mark.django_db
def test_ingredient_save_post_invalid_returns_form(client, recipe, iir):
    response = client.post(
        f"/recipes/{recipe.pk}/ingredients/{iir.pk}/save/",
        {"quantity": "-5", "unit": "kg", "preparation": "", "note": ""},
    )
    assert response.status_code == 200
    assert "<form" in response.content.decode()


@pytest.mark.django_db
def test_ingredient_delete_removes_iir(client, recipe, iir):
    iir_id = iir.pk
    response = client.post(f"/recipes/{recipe.pk}/ingredients/{iir_id}/delete/")
    assert response.status_code == 200
    assert not IngredientInRecipe.objects.filter(pk=iir_id).exists()


@pytest.mark.django_db
def test_ingredient_delete_reorders_remaining(client, recipe, group):
    ing = Ingredient.objects.create(ingredient_name="garlic")
    ing2 = Ingredient.objects.create(ingredient_name="salt")
    i1 = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=0
    )
    i2 = IngredientInRecipe.objects.create(
        ingredient=ing2, ingredient_group=group, index_in_sequence=1
    )
    client.post(f"/recipes/{recipe.pk}/ingredients/{i1.pk}/delete/")
    i2.refresh_from_db()
    assert i2.index_in_sequence == 0


@pytest.mark.django_db
def test_group_display_returns_200(client, recipe, group):
    response = client.get(f"/recipes/{recipe.pk}/groups/{group.pk}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_group_display_no_form_elements(client, recipe, group):
    response = client.get(f"/recipes/{recipe.pk}/groups/{group.pk}/")
    assert "<form" not in response.content.decode()


@pytest.mark.django_db
def test_group_edit_returns_200(client, recipe, group):
    response = client.get(f"/recipes/{recipe.pk}/groups/{group.pk}/edit/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_group_edit_has_form(client, recipe, group):
    response = client.get(f"/recipes/{recipe.pk}/groups/{group.pk}/edit/")
    assert "<form" in response.content.decode()


@pytest.mark.django_db
def test_group_save_post_valid_saves_and_returns_display(client, recipe, group):
    response = client.post(
        f"/recipes/{recipe.pk}/groups/{group.pk}/save/",
        {"group_name": "Sauce"},
    )
    assert response.status_code == 200
    group.refresh_from_db()
    assert group.group_name == "Sauce"
    assert "<form" not in response.content.decode()


@pytest.mark.django_db
def test_group_delete_removes_group(client, recipe, group):
    group_id = group.pk
    response = client.post(f"/recipes/{recipe.pk}/groups/{group_id}/delete/")
    assert response.status_code == 200
    assert not IngredientGroup.objects.filter(pk=group_id).exists()


@pytest.mark.django_db
def test_group_add_creates_group(client, recipe):
    response = client.post(f"/recipes/{recipe.pk}/groups/add/")
    assert response.status_code == 200
    assert IngredientGroup.objects.filter(recipe=recipe).count() == 1


@pytest.mark.django_db
def test_group_add_returns_edit_partial(client, recipe):
    response = client.post(f"/recipes/{recipe.pk}/groups/add/")
    assert "<form" in response.content.decode()
