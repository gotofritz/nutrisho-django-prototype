"""Browser journey: delete a recipe, then Undo, then the trash (#75)."""

import re

import pytest
from playwright.sync_api import Page, expect

from recipes.models import Recipe

pytestmark = pytest.mark.e2e


def test_delete_then_undo_brings_the_recipe_back(signed_in: Page, user, make_recipe):
    """Delete goes on to the next recipe with an Undo toast; Undo reopens the deleted one."""
    soup = make_recipe(owner=user, name="Soup")
    stew = make_recipe(owner=user, name="Stew")
    signed_in.goto(f"/recipes/{soup.pk}/")

    signed_in.locator('[aria-controls="delete-panel"]').click()
    signed_in.get_by_role("button", name="Confirm delete").click()

    expect(signed_in).to_have_url(re.compile(rf"/recipes/{stew.pk}/$"))
    toast = signed_in.locator("[data-toast]")
    expect(toast).to_contain_text("Deleted “Soup”.")
    assert Recipe.objects.trashed().get() == soup

    toast.get_by_role("button", name="Undo").click()

    expect(signed_in).to_have_url(re.compile(rf"/recipes/{soup.pk}/$"))
    expect(signed_in.locator("[data-toast]")).to_contain_text("Restored “Soup”.")
    assert not Recipe.objects.trashed().exists()


def test_a_toast_can_be_dismissed(signed_in: Page, user, make_recipe):
    """The toast's Dismiss button removes it."""
    soup = make_recipe(owner=user, name="Soup")
    signed_in.goto(f"/recipes/{soup.pk}/")
    signed_in.locator('[aria-controls="delete-panel"]').click()
    signed_in.get_by_role("button", name="Confirm delete").click()

    signed_in.get_by_role("button", name="Dismiss").last.click()
    expect(signed_in.locator("[data-toast]")).to_have_count(0)


def test_restore_from_the_trash(signed_in: Page, user, make_recipe):
    """The Trash link lists the deleted recipe; Restore opens it."""
    soup = make_recipe(owner=user, name="Soup")
    soup.deleted_at = soup.created_date
    soup.save(update_fields=["deleted_at"])
    signed_in.goto("/recipes/")

    signed_in.get_by_role("link", name="Trash").click()
    expect(signed_in.locator(".trash-name")).to_have_text(["Soup"])
    signed_in.get_by_role("button", name="Restore").click()

    expect(signed_in).to_have_url(re.compile(rf"/recipes/{soup.pk}/$"))
    assert Recipe.objects.live().get() == soup
