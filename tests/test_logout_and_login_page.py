"""Tests for the log-out control and the login page (#59).

Django's ``LogoutView`` only accepts POST, so every log-out control is a form
that posts to it. Both the log-out and log-in forms opt out of ``hx-boost``:
logging in rotates the CSRF token, and a boosted swap would keep the stale
token in ``<body hx-headers>``.
"""

import re

import pytest
from django.test import Client

from recipes.models import Recipe

LOGIN_URL = "/accounts/login/"
LOGOUT_URL = "/accounts/logout/"


@pytest.fixture
def recipe(user, db) -> Recipe:
    """A recipe owned by the default user."""
    return Recipe.objects.create(recipe_name="Soup", owner=user)


def _logout_form(html: str) -> str:
    match = re.search(
        r'<form[^>]*action="/accounts/logout/"[^>]*>.*?</form>', html, flags=re.DOTALL
    )
    assert match, "log-out form missing"
    return match.group(0)


def _login_form(html: str) -> str:
    match = re.search(r'<form[^>]*method="post"[^>]*>.*?</form>', html, flags=re.DOTALL)
    assert match, "login form missing"
    return match.group(0)


# --- log-out control ---


@pytest.mark.django_db
def test_recipe_list_has_logout_form(auth_client):
    """The recipe list header posts to the log-out view with a CSRF token."""
    html = auth_client.get("/recipes/").content.decode()
    form = _logout_form(html)
    assert 'method="post"' in form
    assert 'name="csrfmiddlewaretoken"' in form
    assert 'type="submit"' in form
    assert "Log out" in form


@pytest.mark.django_db
def test_recipe_navbar_has_logout_form(auth_client, recipe):
    """The recipe page navbar posts to the log-out view."""
    html = auth_client.get(f"/recipes/{recipe.pk}/").content.decode()
    navbar = html[html.index('class="navbar"') :]
    form = _logout_form(navbar)
    assert 'method="post"' in form
    assert 'name="csrfmiddlewaretoken"' in form
    assert 'aria-label="Log out"' in form


@pytest.mark.django_db
def test_boosted_recipe_page_keeps_logout_form(auth_client, recipe):
    """A boosted visit replaces the whole body, so it must carry the navbar's form."""
    response = auth_client.get(
        f"/recipes/{recipe.pk}/", HTTP_HX_REQUEST="true", HTTP_HX_BOOSTED="true"
    )
    _logout_form(response.content.decode())


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/recipes/", "recipe"])
def test_logout_form_is_not_boosted(auth_client, recipe, path):
    """Log-out is a full page load, so the login page arrives with fresh state."""
    url = f"/recipes/{recipe.pk}/" if path == "recipe" else path
    form = _logout_form(auth_client.get(url).content.decode())
    assert 'hx-boost="false"' in form


@pytest.mark.django_db
def test_logout_signs_the_user_out(auth_client):
    """Posting the log-out form ends the session and lands on the login page."""
    response = auth_client.post(LOGOUT_URL)
    assert response.status_code == 302
    assert response["Location"] == LOGIN_URL
    after = auth_client.get("/recipes/")
    assert after.status_code == 302
    assert after["Location"].startswith(LOGIN_URL)


@pytest.mark.django_db
def test_logout_rejects_get(auth_client):
    """A GET (a prefetch or a stray link) must not sign the user out."""
    assert auth_client.get(LOGOUT_URL).status_code == 405
    assert auth_client.get("/recipes/").status_code == 200


# --- login page ---


@pytest.fixture
def login_html(db) -> str:
    """The login page as an anonymous visitor sees it."""
    response = Client().get(LOGIN_URL)
    assert response.status_code == 200
    return response.content.decode()


def test_login_page_extends_base(login_html):
    """The login page carries the app chrome from ``base.html``."""
    assert "<title>Log in</title>" in login_html
    assert "favicon.ico" in login_html
    assert "fonts/lobster/lobster-latin-400.woff2" in login_html
    assert 'id="a11y-status"' in login_html
    assert '<h1 tabindex="-1">Log in</h1>' in login_html


def test_login_page_labels_its_fields(login_html):
    """Each input has a visible label tied to it, not a bare ``form.as_p``."""
    form = _login_form(login_html)
    assert '<label for="id_username"' in form
    assert '<label for="id_password"' in form
    assert 'id="id_username"' in form
    assert 'id="id_password"' in form
    assert 'class="login-form"' in form


def test_login_form_is_not_boosted(login_html):
    """Logging in rotates the CSRF token, so the next page must be a full load."""
    assert 'hx-boost="false"' in _login_form(login_html)


def test_login_page_has_no_logout_form(login_html):
    """An anonymous visitor has nothing to log out of."""
    assert LOGOUT_URL not in login_html


def test_login_page_clears_htmx_history(login_html):
    """The back button must not replay the page snapshots htmx keeps in localStorage."""
    assert "localStorage.removeItem('htmx-history-cache')" in login_html


@pytest.mark.django_db
def test_failed_login_shows_an_alert(user):
    """A wrong password is reported in an alert the screen reader reads out."""
    response = Client().post(LOGIN_URL, {"username": user.username, "password": "wrong"})
    assert response.status_code == 200
    html = response.content.decode()
    match = re.search(
        r'<div[^>]*role="alert"[^>]*class="login-error"[^>]*>(.*?)</div>', html, flags=re.DOTALL
    )
    assert match, "login error alert missing"
    assert "correct username and password" in match.group(1)


@pytest.mark.django_db
def test_failed_login_keeps_username(user):
    """The username survives a failed attempt so only the password is retyped."""
    response = Client().post(LOGIN_URL, {"username": user.username, "password": "wrong"})
    assert f'value="{user.username}"' in response.content.decode()
