"""Tests for recipe field inline-edit views (Plan 004, Step 2)."""

import pytest
from django.test import Client

from recipes.models import Recipe


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def recipe(user, db):
    return Recipe.objects.create(recipe_name="Editable Recipe", owner=user, servings=2)


@pytest.mark.django_db
def test_field_display_get_returns_200(client, recipe):
    response = client.get(f"/recipes/{recipe.pk}/field/recipe_name/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_field_display_no_form_elements(client, recipe):
    response = client.get(f"/recipes/{recipe.pk}/field/recipe_name/")
    content = response.content.decode()
    assert "<form" not in content
    assert "<input" not in content


@pytest.mark.django_db
def test_field_display_shows_current_value(client, recipe):
    response = client.get(f"/recipes/{recipe.pk}/field/recipe_name/")
    assert recipe.recipe_name.encode() in response.content


@pytest.mark.django_db
def test_field_display_unknown_field_returns_404(client, recipe):
    response = client.get(f"/recipes/{recipe.pk}/field/unknown_field/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_field_display_nonexistent_recipe_returns_404(client, db):
    response = client.get("/recipes/99999/field/recipe_name/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_field_edit_get_returns_200(client, recipe):
    response = client.get(f"/recipes/{recipe.pk}/field/recipe_name/edit/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_field_edit_returns_form_with_current_value(client, recipe):
    response = client.get(f"/recipes/{recipe.pk}/field/recipe_name/edit/")
    content = response.content.decode()
    assert "<form" in content
    assert recipe.recipe_name in content


@pytest.mark.django_db
def test_field_edit_cancel_button_points_to_display(client, recipe):
    response = client.get(f"/recipes/{recipe.pk}/field/recipe_name/edit/")
    content = response.content.decode()
    display_url = f"/recipes/{recipe.pk}/field/recipe_name/"
    assert display_url in content


@pytest.mark.django_db
def test_field_edit_unknown_field_returns_404(client, recipe):
    response = client.get(f"/recipes/{recipe.pk}/field/unknown_field/edit/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_field_save_post_valid_saves_and_returns_display(client, recipe):
    response = client.post(
        f"/recipes/{recipe.pk}/field/recipe_name/save/",
        {"recipe_name": "Updated Name"},
    )
    assert response.status_code == 200
    recipe.refresh_from_db()
    assert recipe.recipe_name == "Updated Name"
    content = response.content.decode()
    assert "<form" not in content


@pytest.mark.django_db
def test_field_save_post_invalid_returns_form_with_errors(client, recipe):
    response = client.post(
        f"/recipes/{recipe.pk}/field/recipe_name/save/",
        {"recipe_name": ""},  # required field
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "<form" in content


@pytest.mark.django_db
def test_field_save_nonexistent_recipe_returns_404(client, db):
    response = client.post("/recipes/99999/field/recipe_name/save/", {"recipe_name": "x"})
    assert response.status_code == 404


@pytest.mark.django_db
def test_field_save_get_not_allowed(client, recipe):
    response = client.get(f"/recipes/{recipe.pk}/field/recipe_name/save/")
    assert response.status_code == 405
