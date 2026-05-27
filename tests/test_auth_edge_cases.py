"""Tests for authentication edge cases: next-redirect and HTMX session-expiry."""

import pytest
from django.test import Client

from recipes.models import Recipe


@pytest.fixture
def recipe(user, db):
    return Recipe.objects.create(recipe_name="Deep Link Recipe", owner=user)


# --- `next` parameter preserved through login ---


@pytest.mark.django_db
def test_login_preserves_next_in_form(db):
    """Login page with ?next= must render a hidden <next> field so redirect fires after submit."""
    c = Client()
    response = c.get("/accounts/login/?next=/recipes/99/")
    assert response.status_code == 200
    content = response.content.decode()
    assert 'name="next"' in content
    assert "/recipes/99/" in content


@pytest.mark.django_db
def test_login_next_redirects_after_success(user, db):
    """Successful login with next= must redirect to the target, not LOGIN_REDIRECT_URL."""
    c = Client()
    response = c.post(
        "/accounts/login/?next=/recipes/",
        {"username": user.username, "password": "x"},
    )
    assert response.status_code == 302
    assert response["Location"] == "/recipes/"


# --- HTMX unauthenticated → HX-Redirect, not 302 into panel ---


@pytest.mark.django_db
def test_htmx_unauthenticated_returns_hx_redirect(recipe):
    """HTMX request to protected endpoint with expired session must get HX-Redirect, not 302."""
    c = Client()  # not logged in
    response = c.get(
        f"/recipes/{recipe.pk}/field/recipe_name/",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert "HX-Redirect" in response
    assert "/accounts/login/" in response["HX-Redirect"]


@pytest.mark.django_db
def test_htmx_unauthenticated_post_returns_hx_redirect(recipe):
    """HTMX POST to protected endpoint must get HX-Redirect, not 302."""
    c = Client()
    response = c.post(
        f"/recipes/{recipe.pk}/delete/",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert "HX-Redirect" in response


@pytest.mark.django_db
def test_non_htmx_unauthenticated_still_gets_302(recipe):
    """Plain browser request to protected endpoint must still get normal 302."""
    c = Client()
    response = c.get(f"/recipes/{recipe.pk}/")
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_htmx_post_unauthenticated_next_is_safe(recipe):
    """HTMX POST (e.g. delete) session expiry: next= must not point to the POST URL.
    After login, the browser must not GET a POST-only endpoint."""
    c = Client()
    response = c.post(
        f"/recipes/{recipe.pk}/delete/",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert "HX-Redirect" in response
    hx_redirect = response["HX-Redirect"]
    # next= must not contain the delete URL (POST-only endpoint)
    assert f"/recipes/{recipe.pk}/delete/" not in hx_redirect


@pytest.mark.django_db
def test_htmx_post_unauthenticated_next_is_omitted_or_referer(recipe):
    """HTMX POST with Referer: next= should be Referer, not the POST URL."""
    c = Client()
    response = c.post(
        f"/recipes/{recipe.pk}/scale/",
        {"multiplier": "2"},
        HTTP_HX_REQUEST="true",
        HTTP_REFERER=f"http://testserver/recipes/{recipe.pk}/",
    )
    assert response.status_code == 200
    hx_redirect = response["HX-Redirect"]
    # next= should NOT be the POST URL
    assert f"/recipes/{recipe.pk}/scale/" not in hx_redirect


@pytest.mark.django_db
def test_htmx_get_panel_uses_referer_not_panel_url(recipe):
    """HTMX GET to fragment endpoint must use Referer as next=, not the panel URL."""
    c = Client()
    response = c.get(
        f"/recipes/{recipe.pk}/field/recipe_name/",
        HTTP_HX_REQUEST="true",
        HTTP_REFERER=f"http://testserver/recipes/{recipe.pk}/",
    )
    assert response.status_code == 200
    assert "HX-Redirect" in response
    hx_redirect = response["HX-Redirect"]
    # next= must point to the recipe page, not the fragment endpoint
    assert f"/recipes/{recipe.pk}/field/" not in hx_redirect
    assert f"/recipes/{recipe.pk}/" in hx_redirect


@pytest.mark.django_db
def test_htmx_get_panel_no_referer_omits_next(recipe):
    """HTMX GET without Referer must omit next= entirely (can't infer safe redirect)."""
    c = Client()
    response = c.get(
        f"/recipes/{recipe.pk}/field/recipe_name/",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert "HX-Redirect" in response
    assert "next=" not in response["HX-Redirect"]


@pytest.mark.django_db
def test_non_htmx_get_uses_current_url_as_next(recipe):
    """Non-HTMX GET to real page must still use current URL as next=."""
    c = Client()
    response = c.get(f"/recipes/{recipe.pk}/")
    assert response.status_code == 302
    assert f"/recipes/{recipe.pk}/" in response["Location"]


@pytest.mark.django_db
def test_htmx_boosted_get_uses_current_url_not_referer(recipe):
    """Boosted navigation is full-page; next= must be the destination URL, not Referer."""
    c = Client()
    response = c.get(
        f"/recipes/{recipe.pk}/",
        HTTP_HX_REQUEST="true",
        HTTP_HX_BOOSTED="true",
        HTTP_REFERER="http://testserver/recipes/",
    )
    assert response.status_code == 200
    hx_redirect = response["HX-Redirect"]
    # next= must be the recipe detail page, not the list Referer
    assert f"next=/recipes/{recipe.pk}/" in hx_redirect


@pytest.mark.django_db
def test_htmx_boosted_post_uses_referer_not_post_url(recipe):
    """Boosted POST (e.g. Duplicate form) with expired session must not use the POST URL as next=.
    After login the browser must not GET a POST-only endpoint."""
    c = Client()  # not logged in
    response = c.post(
        f"/recipes/{recipe.pk}/duplicate/",
        HTTP_HX_REQUEST="true",
        HTTP_HX_BOOSTED="true",
        HTTP_REFERER="http://testserver/recipes/",
    )
    assert response.status_code == 200
    assert "HX-Redirect" in response
    hx_redirect = response["HX-Redirect"]
    # next= must NOT be the POST-only duplicate URL
    assert f"/recipes/{recipe.pk}/duplicate/" not in hx_redirect
    # next= should use Referer (/recipes/) instead
    assert "next=/recipes/" in hx_redirect
