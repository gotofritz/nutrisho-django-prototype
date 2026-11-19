"""Browser journey: download an export, then import it from the header's page (#78)."""

import json
import re

import pytest
from playwright.sync_api import Page, expect

from recipes.models import Recipe

pytestmark = pytest.mark.e2e


def test_export_then_import_from_the_page(signed_in: Page, user, make_recipe):
    """Config leads to the page; the download re-imports as a renamed copy."""
    make_recipe(owner=user, name="Soup")
    signed_in.goto("/recipes/")
    signed_in.get_by_role("link", name="Config").click()
    signed_in.get_by_role("link", name="Import & export").click()
    expect(signed_in.get_by_role("heading", name="Import and export")).to_be_visible()

    with signed_in.expect_download() as download:
        signed_in.get_by_role("link", name="Download my recipes").click()
    path = download.value.path()
    assert json.loads(path.read_text())["recipes"][0]["recipe_name"] == "Soup"

    signed_in.get_by_label("File to import").set_input_files(path)
    signed_in.get_by_role("button", name="Import", exact=True).click()

    expect(signed_in.get_by_role("heading", name="Imported 1 recipe")).to_be_visible()
    signed_in.get_by_role("link", name="Soup Imported").click()
    expect(signed_in).to_have_url(re.compile(r"/recipes/[0-9a-f-]{36}/$"))
    assert Recipe.objects.filter(owner=user).count() == 2
