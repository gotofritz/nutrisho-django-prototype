"""Cross-user ownership enforcement: logged-in user must get 404 for another user's recipes."""

import pytest
from django.contrib.auth.models import User
from django.test import Client

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="owner", password="x")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="other", password="x")


@pytest.fixture
def owner_client(owner):
    c = Client()
    c.force_login(owner)
    return c


@pytest.fixture
def other_client(other):
    c = Client()
    c.force_login(other)
    return c


@pytest.fixture
def recipe(owner, db):
    return Recipe.objects.create(recipe_name="Owner Recipe", owner=owner)


@pytest.fixture
def step(recipe):
    return Step.objects.create(recipe=recipe, step_text="step", index_in_sequence=0)


@pytest.fixture
def group(recipe):
    return IngredientGroup.objects.create(recipe=recipe, group_name="g", index_in_sequence=0)


@pytest.fixture
def iir(group):
    ing = Ingredient.objects.create(ingredient_name="onion-own")
    return IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=0
    )


# --- Recipe detail ---


@pytest.mark.django_db
def test_other_user_cannot_view_recipe(other_client, recipe):
    response = other_client.get(f"/recipes/{recipe.pk}/")
    assert response.status_code == 404


# --- Metadata ---


@pytest.mark.django_db
def test_other_user_cannot_get_metadata(other_client, recipe):
    response = other_client.get(f"/recipes/{recipe.pk}/metadata/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_other_user_cannot_post_metadata(other_client, recipe):
    response = other_client.post(f"/recipes/{recipe.pk}/metadata/", {"recipe_name": "Hijacked"})
    assert response.status_code == 404


# --- Delete ---


@pytest.mark.django_db
def test_other_user_cannot_delete(other_client, recipe):
    response = other_client.post(f"/recipes/{recipe.pk}/delete/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_other_user_cannot_get_delete_panel(other_client, recipe):
    response = other_client.get(f"/recipes/{recipe.pk}/delete/panel/", HTTP_HX_REQUEST="true")
    assert response.status_code == 404


# --- Scale ---


@pytest.mark.django_db
def test_other_user_cannot_scale(other_client, recipe):
    response = other_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "2"})
    assert response.status_code == 404


@pytest.mark.django_db
def test_other_user_cannot_get_scale_panel(other_client, recipe):
    response = other_client.get(f"/recipes/{recipe.pk}/scale/panel/", HTTP_HX_REQUEST="true")
    assert response.status_code == 404


# --- Duplicate ---


@pytest.mark.django_db
def test_other_user_cannot_duplicate(other_client, recipe):
    response = other_client.post(f"/recipes/{recipe.pk}/duplicate/")
    assert response.status_code == 404


# --- Fields ---


@pytest.mark.django_db
def test_other_user_cannot_view_field(other_client, recipe):
    response = other_client.get(f"/recipes/{recipe.pk}/field/recipe_name/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_other_user_cannot_edit_field(other_client, recipe):
    response = other_client.get(f"/recipes/{recipe.pk}/field/recipe_name/edit/")
    assert response.status_code == 404


# --- Steps ---


@pytest.mark.django_db
def test_other_user_cannot_view_step(other_client, recipe, step):
    response = other_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_other_user_cannot_add_step(other_client, recipe):
    response = other_client.post(f"/recipes/{recipe.pk}/steps/add/")
    assert response.status_code == 404


# --- Ingredients ---


@pytest.mark.django_db
def test_other_user_cannot_view_ingredient(other_client, recipe, iir):
    response = other_client.get(f"/recipes/{recipe.pk}/ingredients/{iir.pk}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_other_user_cannot_add_ingredient(other_client, recipe, group):
    response = other_client.post(f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/add/")
    assert response.status_code == 404


# --- Groups ---


@pytest.mark.django_db
def test_other_user_cannot_view_group(other_client, recipe, group):
    response = other_client.get(f"/recipes/{recipe.pk}/groups/{group.pk}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_other_user_cannot_add_group(other_client, recipe):
    response = other_client.post(f"/recipes/{recipe.pk}/groups/add/")
    assert response.status_code == 404


# --- Delete empty-state with two users ---


@pytest.mark.django_db
def test_delete_last_recipe_shows_empty_state_when_other_user_has_recipes(
    owner_client, owner, other, recipe
):
    """Owner deletes their only recipe; other user still has one.
    Should still show empty state for owner (not rely on global exists())."""
    Recipe.objects.create(recipe_name="Other's Recipe", owner=other)
    response = owner_client.post(
        f"/recipes/{recipe.pk}/delete/",
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET=f"recipe-{recipe.pk}",
    )
    assert response.status_code == 200
    assert "No recipes are available." in response.content.decode()
    assert response["HX-Retarget"] == "#recipe-list"
