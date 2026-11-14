"""Resting on a control shows which keys work it (#60).

A pointer that rests on a control, or keyboard focus that stays on one, shows a
hint after a pause naming the key or keys that activate it. Playwright's clock
skips the pause instead of waiting it out.
"""

import pytest
from playwright.sync_api import Page, expect

from recipes.models import Recipe
from tests.recipes.e2e.htmx import settled

pytestmark = pytest.mark.e2e

PAUSE_MS = 2000


@pytest.fixture
def recipe(make_recipe, user, add_step, add_ingredient, make_ingredient) -> Recipe:
    """A recipe with a step and an ingredient, owned by the signed-in user."""
    recipe = make_recipe(owner=user, name="Risotto")
    add_step(recipe=recipe, text="Toast the rice.")
    add_ingredient(recipe=recipe, ingredient=make_ingredient("rice"))
    return recipe


@pytest.fixture
def editing(signed_in: Page, recipe: Recipe) -> Page:
    """The recipe in edit mode, with the page's clock under the test's control."""
    signed_in.clock.install()
    signed_in.goto(f"/recipes/{recipe.pk}/?edit=1")
    return signed_in


def _hint(page: Page):
    return page.locator("#key-hint")


def test_hovering_a_button_shows_its_keys_only_after_a_pause(editing: Page):
    """A pointer resting on a button shows Enter and Space, but not at once."""
    editing.get_by_role("button", name="+ Add step").hover()

    editing.clock.run_for(PAUSE_MS - 500)
    expect(_hint(editing)).to_be_hidden()
    editing.clock.run_for(600)
    expect(_hint(editing)).to_be_visible()
    expect(_hint(editing)).to_contain_text("Enter")
    expect(_hint(editing)).to_contain_text("Space")


def test_moving_away_hides_the_hint(editing: Page):
    """The hint goes when the pointer leaves the control."""
    editing.get_by_role("button", name="+ Add step").hover()
    editing.clock.run_for(PAUSE_MS + 100)
    expect(_hint(editing)).to_be_visible()

    editing.mouse.move(0, 0)

    expect(_hint(editing)).to_be_hidden()


def test_keyboard_focus_on_a_link_shows_enter(editing: Page):
    """Focus that stays on a link names Enter, the one key that follows it."""
    editing.get_by_role("link", name="Done editing").focus()

    editing.clock.run_for(PAUSE_MS + 100)

    expect(_hint(editing)).to_be_visible()
    expect(_hint(editing)).to_contain_text("Enter")
    expect(_hint(editing)).not_to_contain_text("Space")


def test_a_key_press_hides_the_hint(editing: Page):
    """Any key, Escape included, puts the hint away."""
    editing.get_by_role("link", name="Done editing").focus()
    editing.clock.run_for(PAUSE_MS + 100)
    expect(_hint(editing)).to_be_visible()

    editing.keyboard.press("Shift")

    expect(_hint(editing)).to_be_hidden()


def test_a_checkbox_names_space(editing: Page):
    """A tick box is worked with Space."""
    editing.get_by_role("checkbox", name="Select rice").focus()

    editing.clock.run_for(PAUSE_MS + 100)

    expect(_hint(editing)).to_contain_text("Space")
    expect(_hint(editing)).not_to_contain_text("Enter")


def test_a_field_in_an_inline_editor_names_save_and_cancel(editing: Page):
    """In an editor's field, Enter saves and Escape cancels, named after the buttons."""
    editing.get_by_role("button", name="Toast the rice.", exact=True).press("Enter")
    title = editing.get_by_role("textbox", name="Step title (optional)")
    expect(title).to_be_focused()
    settled(editing)

    editing.clock.run_for(PAUSE_MS + 100)

    expect(_hint(editing)).to_contain_text("Enter")
    expect(_hint(editing)).to_contain_text("save")
    expect(_hint(editing)).to_contain_text("Esc")
    expect(_hint(editing)).to_contain_text("cancel")


def test_a_titled_control_shows_its_title_in_the_hint_instead(editing: Page):
    """The browser's own title tooltip would cover the hint, so the hint carries it."""
    editing.get_by_role("button", name="Toast the rice.", exact=True).click()
    split = editing.get_by_role("button", name="Split at cursor")
    settled(editing)

    split.hover()
    expect(split).not_to_have_attribute("title", "Split this step in two where the cursor is")
    editing.clock.run_for(PAUSE_MS + 100)

    expect(_hint(editing)).to_contain_text("Split this step in two where the cursor is")
    editing.mouse.move(0, 0)
    expect(split).to_have_attribute("title", "Split this step in two where the cursor is")


def test_a_click_shows_no_hint(editing: Page):
    """Pressing a control is using it: no hint follows for the pointer resting there."""
    editing.get_by_role("checkbox", name="Select rice").click()

    editing.clock.run_for(PAUSE_MS + 100)

    expect(_hint(editing)).to_be_hidden()
