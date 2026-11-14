"""Browser journey: logging in and out (#63)."""

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_logging_in_returns_to_the_page_asked_for(page: Page, user, make_recipe):
    """A signed-out visit goes to the login page, and logging in comes back."""
    make_recipe(owner=user, name="Lentil soup")

    page.goto("/recipes/")
    expect(page).to_have_url(re.compile(r"/accounts/login/\?next=/recipes/$"))

    page.get_by_label("Username").fill(user.username)
    page.get_by_label("Password").fill("x")
    page.get_by_role("button", name="Log in").click()

    expect(page).to_have_url(re.compile(r"/recipes/$"))
    expect(page.get_by_role("link", name="Lentil soup", exact=True)).to_be_visible()


def test_a_wrong_password_is_refused(page: Page, user):
    """A bad password keeps the user on the login page with an error."""
    page.goto("/accounts/login/")

    page.get_by_label("Username").fill(user.username)
    page.get_by_label("Password").fill("wrong")
    page.get_by_role("button", name="Log in").click()

    expect(page.get_by_role("alert").filter(has_text="correct username")).to_be_visible()
    expect(page).to_have_url(re.compile(r"/accounts/login/$"))


def test_logging_out_lands_on_the_login_page(signed_in: Page):
    """Log out ends the session: the recipe list then asks to log in again."""
    signed_in.goto("/recipes/")
    signed_in.get_by_role("button", name="Log out").click()

    expect(signed_in.get_by_role("button", name="Log in")).to_be_visible()
    signed_in.goto("/recipes/")
    expect(signed_in).to_have_url(re.compile(r"/accounts/login/"))
