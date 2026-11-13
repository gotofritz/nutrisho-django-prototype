"""Browser journeys: the banner shown when an htmx save fails (#37, #63)."""

import pytest
from playwright.sync_api import Page, Route, expect

from recipes.models import Recipe
from tests.recipes.e2e.htmx import settled

pytestmark = pytest.mark.e2e


@pytest.fixture
def editing(signed_in: Page, make_recipe, user, add_step) -> Page:
    """The recipe page with its one step's edit form open."""
    recipe = make_recipe(owner=user, name="Bread")
    add_step(recipe=recipe, text="Knead the dough.")
    signed_in.goto(f"/recipes/{recipe.pk}/")
    signed_in.locator(".step-content").click()
    expect(signed_in.get_by_placeholder("Title (optional)")).to_be_focused()
    settled(signed_in)
    return signed_in


def test_a_refused_save_shows_the_banner_and_keeps_the_text(editing: Page):
    """A 404 (the recipe was deleted elsewhere) is not swapped: the typed text stays."""
    Recipe.objects.all().delete()
    banner = editing.locator("#save-error")
    expect(banner).to_be_hidden()

    editing.get_by_placeholder("New step").fill("Knead the dough for ten minutes.")
    editing.get_by_role("button", name="Save").click()

    expect(banner).to_be_visible()
    expect(banner).to_contain_text("Your change was not saved. Reload the page and try again.")
    expect(editing.get_by_placeholder("New step")).to_have_value("Knead the dough for ten minutes.")

    editing.get_by_role("button", name="Dismiss").click()
    expect(banner).to_be_hidden()


def test_a_dropped_connection_shows_the_banner_until_a_save_succeeds(editing: Page):
    """A network failure asks the user to check the connection; the next save clears it."""
    banner = editing.locator("#save-error")

    def drop(route: Route) -> None:
        route.abort()

    editing.route("**/save/", drop)
    editing.get_by_placeholder("New step").fill("Knead the dough for ten minutes.")
    editing.get_by_role("button", name="Save").click()
    expect(banner).to_contain_text("Check your connection and try again.")
    expect(banner).to_be_visible()

    editing.unroute("**/save/", drop)
    editing.get_by_role("button", name="Save").click()
    expect(editing.locator(".step-content")).to_have_text("Knead the dough for ten minutes.")
    expect(banner).to_be_hidden()
