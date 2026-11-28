"""Browser journey: make an API key, copy it, revoke it (#150)."""

import pytest
from playwright.sync_api import Page, expect

from recipes.models import ApiToken
from recipes.services.api_tokens import user_for_key

pytestmark = pytest.mark.e2e


def test_make_copy_and_revoke_a_key(signed_in: Page, user):
    """Config leads to the page; a new key is shown once and copies; Revoke asks first."""
    signed_in.context.grant_permissions(["clipboard-read", "clipboard-write"])
    signed_in.goto("/recipes/config/")
    signed_in.get_by_role("link", name="API keys").click()

    signed_in.get_by_label("Name").fill("Firefox clipper")
    signed_in.get_by_role("button", name="Make a key").click()
    # Copy works once the new page has run app.js, which is deferred; the
    # click returns as soon as that page starts loading (#211's flaky run).
    signed_in.wait_for_load_state()

    key_box = signed_in.get_by_label("New API key")
    key = key_box.input_value()
    assert user_for_key(key) == user
    signed_in.get_by_role("button", name="Copy").click()
    expect(signed_in.get_by_role("button", name="Copied")).to_be_visible()
    assert signed_in.evaluate("navigator.clipboard.readText()") == key

    signed_in.once("dialog", lambda dialog: dialog.accept())
    signed_in.get_by_role("button", name="Revoke").click()
    expect(signed_in.get_by_text("Revoked “Firefox clipper”.")).to_be_visible()
    expect(signed_in.get_by_text("You have no API keys yet.")).to_be_visible()
    assert not ApiToken.objects.exists()
