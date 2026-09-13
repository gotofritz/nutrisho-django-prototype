"""Tests for HTMX integration (Plan 002)."""

import re

import pytest
from django.test import Client

from recipes.models import Recipe


@pytest.fixture
def auth_client(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def recipe(user, db):
    return Recipe.objects.create(recipe_name="HTMX Test Recipe", owner=user)


@pytest.mark.django_db
def test_htmx_middleware_injects_attribute(auth_client):
    """django-htmx middleware injects request.htmx on every request."""
    from django.conf import settings

    assert "django_htmx.middleware.HtmxMiddleware" in settings.MIDDLEWARE


@pytest.mark.django_db
def test_htmx_installed_app():
    """django_htmx in INSTALLED_APPS."""
    from django.conf import settings

    assert "django_htmx" in settings.INSTALLED_APPS


@pytest.mark.django_db
def test_recipe_view_htmx_request_returns_partial(auth_client, recipe):
    """HTMX request to recipe view returns fragment without html/body tags."""
    response = auth_client.get(
        f"/recipes/{recipe.pk}/",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "<html" not in content
    assert "<body" not in content


@pytest.mark.django_db
def test_recipe_view_normal_request_returns_full_page(auth_client, recipe):
    """Normal request returns full HTML page."""
    response = auth_client.get(f"/recipes/{recipe.pk}/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "<html" in content
    assert "<body" in content


@pytest.mark.django_db
def test_base_template_renders_without_error(auth_client):
    """Base template renders without error (home page uses it)."""
    response = auth_client.get("/recipes/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_recipe_view_vary_header(auth_client, recipe):
    """recipe() sets Vary: HX-Request to prevent cache poisoning."""
    response = auth_client.get(f"/recipes/{recipe.pk}/")
    assert "HX-Request" in response.get("Vary", "")


@pytest.mark.django_db
def test_recipe_htmx_response_contains_title(auth_client, recipe):
    """HTMX partial for recipe includes <title> OOB swap for tab title update."""
    response = auth_client.get(f"/recipes/{recipe.pk}/", HTTP_HX_REQUEST="true")
    content = response.content.decode()
    assert "<title" in content
    assert recipe.recipe_name in content


@pytest.mark.django_db
def test_recipe_full_page_has_no_title_in_body(auth_client, recipe):
    """Normal (non-HTMX) recipe page must not have <title> inside <body>."""
    response = auth_client.get(f"/recipes/{recipe.pk}/")
    content = response.content.decode()
    # <title> must appear only in <head>, not after <body>
    body_start = content.index("<body")
    assert "<title" not in content[body_start:]


@pytest.mark.django_db
def test_home_htmx_request_returns_200(auth_client):
    """Home view returns 200 for boosted HTMX navigation."""
    response = auth_client.get("/recipes/", HTTP_HX_REQUEST="true")
    assert response.status_code == 200


@pytest.mark.django_db
def test_home_htmx_response_has_no_title_in_body(auth_client):
    """Home view response must not have <title> inside <body> (valid for hx-boost extraction)."""
    response = auth_client.get("/recipes/", HTTP_HX_REQUEST="true")
    content = response.content.decode()
    body_start = content.index("<body")
    assert "<title" not in content[body_start:]


@pytest.mark.django_db
def test_home_page_title_populated(auth_client):
    """Home page must render a non-empty <title> in <head>."""
    response = auth_client.get("/recipes/")
    content = response.content.decode()
    head_end = content.index("</head>")
    head = content[:head_end]
    assert "<title>Recipes</title>" in head


@pytest.mark.django_db
def test_base_template_has_csrf_header_for_htmx(auth_client):
    """Body element carries hx-headers with X-CSRFToken so HTMX POSTs aren't rejected."""
    response = auth_client.get("/recipes/")
    content = response.content.decode()
    assert "hx-headers=" in content
    assert "X-CSRFToken" in content


@pytest.mark.django_db
def test_base_template_htmx_script_exists_in_static_files(auth_client):
    """The htmx bundle base.html asks for must actually ship with django-htmx.

    django-htmx serves versioned filenames (htmx-2.min.js, htmx-4.min.js); a
    plain htmx.min.js 404s silently and every hx-* attribute in the app becomes
    inert, with nothing failing loudly.
    """
    from django.contrib.staticfiles import finders

    html = auth_client.get("/recipes/").content.decode()
    match = re.search(r'src="/static/(django_htmx/[^"]+\.js)"', html)
    assert match is not None, "base.html no longer loads an htmx bundle"
    assert finders.find(match.group(1)) is not None, f"{match.group(1)} is not on the static path"
