"""Tests for recipes views."""

import pytest
from django.test import Client

from recipes.models import Recipe, Step


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def recipe(user, db):
    return Recipe.objects.create(recipe_name="Test Recipe", owner=user)


@pytest.fixture
def two_recipes(user, db):
    r1 = Recipe.objects.create(recipe_name="First", owner=user)
    r2 = Recipe.objects.create(recipe_name="Second", owner=user)
    return r1, r2


@pytest.mark.django_db
def test_home_view_returns_200(client):
    response = client.get("/recipes/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_home_view_lists_recipes(client, recipe):
    response = client.get("/recipes/")
    assert response.status_code == 200
    assert recipe in response.context["latest_recipe_list"]


@pytest.mark.django_db
def test_recipe_view_returns_200(client, recipe):
    response = client.get(f"/recipes/{recipe.pk}/")
    assert response.status_code == 200
    assert response.context["recipe"] == recipe


@pytest.mark.django_db
def test_recipe_view_404_on_missing(client, db):
    response = client.get("/recipes/99999/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_recipe_nav_single_recipe_wraps_to_self(client, recipe):
    response = client.get(f"/recipes/{recipe.pk}/")
    nav = response.context["nav"]
    assert nav["prev_id"] == recipe.pk
    assert nav["next_id"] == recipe.pk


@pytest.mark.django_db
def test_recipe_nav_wraps_at_boundaries(client, two_recipes):
    first, second = two_recipes
    # At last recipe, next wraps to first
    response = client.get(f"/recipes/{second.pk}/")
    nav = response.context["nav"]
    assert nav["next_id"] == first.pk
    # At first recipe, prev wraps to last
    response = client.get(f"/recipes/{first.pk}/")
    nav = response.context["nav"]
    assert nav["prev_id"] == second.pk


@pytest.mark.django_db
def test_recipe_edit_get_returns_200(client, recipe):
    response = client.get(f"/recipes/{recipe.pk}/edit")
    assert response.status_code == 200
    assert "form" in response.context


@pytest.mark.django_db
def test_recipe_edit_get_prepopulates_name(client, recipe):
    response = client.get(f"/recipes/{recipe.pk}/edit")
    form = response.context["form"]
    assert form["recipe_name"].value() == recipe.recipe_name


@pytest.mark.django_db
def test_recipe_edit_post_returns_200(client, recipe):
    response = client.post(
        f"/recipes/{recipe.pk}/edit",
        {"recipe_name": "Updated Name", "short_description": ""},
    )
    assert response.status_code == 200
