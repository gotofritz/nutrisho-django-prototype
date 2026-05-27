"""Tests for recipe create/delete views (Plan 004, Step 2)."""

import pytest
from django.test import Client

from recipes.models import Recipe


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def recipe(user, db):
    return Recipe.objects.create(recipe_name="Delete Me", owner=user)


@pytest.mark.django_db
def test_recipe_new_get_returns_200(client):
    response = client.get("/recipes/new/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_recipe_new_get_has_form(client):
    response = client.get("/recipes/new/")
    assert "form" in response.context


@pytest.mark.django_db
def test_recipe_new_post_valid_creates_recipe_and_redirects(client, user):
    response = client.post("/recipes/new/", {"recipe_name": "Brand New Recipe"})
    assert response.status_code == 302
    assert Recipe.objects.filter(recipe_name="Brand New Recipe").exists()


@pytest.mark.django_db
def test_recipe_new_post_invalid_returns_200_with_errors(client, user):
    # Empty recipe_name is invalid (required field)
    response = client.post("/recipes/new/", {"recipe_name": ""})
    assert response.status_code == 200
    assert "form" in response.context
    assert response.context["form"].errors


@pytest.mark.django_db
def test_recipe_new_post_duplicate_name_returns_error(client, recipe):
    response = client.post("/recipes/new/", {"recipe_name": recipe.recipe_name})
    assert response.status_code == 200
    assert "form" in response.context


@pytest.mark.django_db
def test_recipe_delete_removes_recipe(client, recipe):
    recipe_id = recipe.pk
    response = client.post(f"/recipes/{recipe_id}/delete/")
    assert response.status_code == 200
    assert not Recipe.objects.filter(pk=recipe_id).exists()


@pytest.mark.django_db
def test_recipe_delete_returns_hx_redirect_header(client, recipe):
    response = client.post(f"/recipes/{recipe.pk}/delete/")
    assert "HX-Redirect" in response
    assert response["HX-Redirect"] == "/recipes/"


@pytest.mark.django_db
def test_recipe_delete_404_on_missing(client, db):
    response = client.post("/recipes/99999/delete/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_recipe_delete_get_not_allowed(client, recipe):
    response = client.get(f"/recipes/{recipe.pk}/delete/")
    assert response.status_code == 405
