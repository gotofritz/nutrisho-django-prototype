"""Tests for HTMX integration (Plan 002)."""

import pytest
from django.test import Client

from recipes.models import Recipe


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def recipe(user, db):
    return Recipe.objects.create(recipe_name="HTMX Test Recipe", owner=user)


@pytest.mark.django_db
def test_htmx_middleware_injects_attribute(client):
    """django-htmx middleware injects request.htmx on every request."""
    from django.conf import settings

    assert "django_htmx.middleware.HtmxMiddleware" in settings.MIDDLEWARE


@pytest.mark.django_db
def test_htmx_installed_app():
    """django_htmx in INSTALLED_APPS."""
    from django.conf import settings

    assert "django_htmx" in settings.INSTALLED_APPS


@pytest.mark.django_db
def test_recipe_view_htmx_request_returns_partial(client, recipe):
    """HTMX request to recipe view returns fragment without html/body tags."""
    response = client.get(
        f"/recipes/{recipe.pk}/",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "<html" not in content
    assert "<body" not in content


@pytest.mark.django_db
def test_recipe_view_normal_request_returns_full_page(client, recipe):
    """Normal request returns full HTML page."""
    response = client.get(f"/recipes/{recipe.pk}/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "<html" in content
    assert "<body" in content


@pytest.mark.django_db
def test_base_template_renders_without_error(client):
    """Base template renders without error (home page uses it)."""
    response = client.get("/recipes/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_recipe_edit_htmx_request_returns_partial(client, recipe):
    """HTMX request to edit view returns fragment without html/body tags."""
    response = client.get(
        f"/recipes/{recipe.pk}/edit",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "<html" not in content
    assert "<body" not in content


@pytest.mark.django_db
def test_recipe_edit_normal_request_returns_full_page(client, recipe):
    """Normal request to edit view returns full HTML page."""
    response = client.get(f"/recipes/{recipe.pk}/edit")
    assert response.status_code == 200
    content = response.content.decode()
    assert "<html" in content
    assert "<body" in content
