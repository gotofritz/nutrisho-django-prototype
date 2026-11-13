"""Browser journeys: adding, editing, moving, splitting, merging and deleting steps (#63)."""

import pytest
from playwright.sync_api import Dialog, Locator, Page, expect

from recipes.models import Recipe, Step
from tests.recipes.e2e.htmx import settled

pytestmark = pytest.mark.e2e


@pytest.fixture
def recipe(make_recipe, user) -> Recipe:
    """A recipe owned by the signed-in user."""
    return make_recipe(owner=user, name="Risotto")


def _open(page: Page, recipe: Recipe) -> Locator:
    """Open the recipe page and return its step texts, in page order."""
    page.goto(f"/recipes/{recipe.pk}/")
    return page.locator("#steps-list > li.step .step-content")


def _edit_form(page: Page) -> Locator:
    """The open step form, once its swap has settled and its title has focus.

    The title's `autofocus` is applied when the swap settles; typing before
    then can land in the field that takes focus mid-way.
    """
    form = page.locator("#steps-list > li.is-editing").last
    expect(form.get_by_placeholder("Title (optional)")).to_be_focused()
    settled(page)
    return form


def _stored(recipe: Recipe) -> list[str]:
    """The recipe's step texts as stored, in sequence."""
    return list(
        Step.objects.filter(recipe=recipe)
        .order_by("index_in_sequence")
        .values_list("step_text", flat=True)
    )


def test_new_steps_land_where_their_drafts_sit(signed_in: Page, recipe, add_step):
    """Two open drafts saved out of order keep their on-screen order (position calculation)."""
    add_step(recipe=recipe, text="Toast the rice.")
    steps = _open(signed_in, recipe)

    signed_in.get_by_role("button", name="+ Add step").click()
    _edit_form(signed_in)
    signed_in.get_by_role("button", name="+ Add step").click()
    drafts = signed_in.locator("#steps-list > li.is-editing")
    expect(drafts).to_have_count(2)
    _edit_form(signed_in)
    drafts.nth(0).get_by_placeholder("New step").fill("Add the stock.")
    drafts.nth(1).get_by_placeholder("New step").fill("Stir in the butter.")

    drafts.nth(1).get_by_role("button", name="Save").click()
    expect(steps).to_have_text(["Toast the rice.", "Stir in the butter."])
    drafts.nth(0).get_by_role("button", name="Save").click()

    expected = ["Toast the rice.", "Add the stock.", "Stir in the butter."]
    expect(steps).to_have_text(expected)
    assert _stored(recipe) == expected


def test_a_draft_can_be_cancelled_without_a_request(signed_in: Page, recipe, add_step):
    """Cancel on a draft removes it from the page and stores nothing."""
    add_step(recipe=recipe, text="Toast the rice.")
    _open(signed_in, recipe)

    signed_in.get_by_role("button", name="+ Add step").click()
    _edit_form(signed_in).get_by_role("button", name="Cancel").click()

    expect(signed_in.locator("li.is-editing")).to_have_count(0)
    assert _stored(recipe) == ["Toast the rice."]


def test_editing_a_step_saves_its_title_and_text(signed_in: Page, recipe, add_step):
    """Clicking a step opens its form in place; Save swaps the display back."""
    add_step(recipe=recipe, text="Toast the rice.")
    steps = _open(signed_in, recipe)

    steps.first.click()
    form = _edit_form(signed_in)
    form.get_by_placeholder("Title (optional)").fill("Base")
    form.get_by_placeholder("New step").fill("Toast the rice for two minutes.")
    form.get_by_role("button", name="Save").click()

    expect(steps).to_have_text(["Base: Toast the rice for two minutes."])
    expect(signed_in.locator(".step-title")).to_have_text("Base")
    assert _stored(recipe) == ["Toast the rice for two minutes."]


def test_moving_a_step_down_reorders_the_list(signed_in: Page, recipe, add_step):
    """The move buttons swap a step with its neighbour."""
    first = add_step(recipe=recipe, text="Toast the rice.")
    add_step(recipe=recipe, text="Add the stock.")
    steps = _open(signed_in, recipe)

    signed_in.locator(f"#step-{first.pk}-down").click()

    expect(steps).to_have_text(["Add the stock.", "Toast the rice."])
    assert _stored(recipe) == ["Add the stock.", "Toast the rice."]


def test_split_at_cursor_counts_code_points_across_a_line_break(signed_in: Page, recipe, add_step):
    """The offset `app.js` posts matches the server's count of the typed text.

    Emoji are two UTF-16 units but one code point, and a line break is posted
    as CRLF but is one character in the textarea. A miscount of either moves
    the cut past `Go` and into `on.`.
    """
    add_step(recipe=recipe, text="placeholder")
    steps = _open(signed_in, recipe)

    steps.first.click()
    text = _edit_form(signed_in).get_by_placeholder("New step")
    text.fill("Melt the\n🧈🧈🧈 butter. Go on.")
    for _ in "Go on.":
        text.press("ArrowLeft")
    signed_in.get_by_role("button", name="Split at cursor").click()

    expect(steps).to_have_text(["Melt the 🧈🧈🧈 butter.", "Go on."])
    assert _stored(recipe) == ["Melt the\n🧈🧈🧈 butter.", "Go on."]


def test_a_split_with_a_blank_half_keeps_the_form_open(signed_in: Page, recipe, add_step):
    """A cursor before the first word answers 422 into the form, typed text kept."""
    add_step(recipe=recipe, text="Toast the rice.")
    steps = _open(signed_in, recipe)

    steps.first.click()
    text = _edit_form(signed_in).get_by_placeholder("New step")
    text.press("Control+Home")
    signed_in.get_by_role("button", name="Split at cursor").click()

    expect(signed_in.locator("li.is-editing").get_by_role("alert")).to_be_visible()
    expect(text).to_have_value("Toast the rice.")
    assert _stored(recipe) == ["Toast the rice."]


def test_the_selection_panel_follows_the_checkboxes(signed_in: Page, recipe, add_step):
    """The bulk panel shows the count, enables Merge from two, and Cancel clears it."""
    for text in ("One.", "Two.", "Three."):
        add_step(recipe=recipe, text=text)
    _open(signed_in, recipe)
    boxes = signed_in.locator(".step-select")
    panel = signed_in.locator("#steps-panel")
    merge = panel.get_by_role("button", name="Merge")
    expect(panel).to_be_hidden()

    boxes.nth(0).check()
    expect(panel).to_be_visible()
    expect(panel).to_contain_text("1 step selected")
    expect(merge).to_be_disabled()

    boxes.nth(2).check()
    expect(panel).to_contain_text("2 steps selected")
    expect(merge).to_be_enabled()

    panel.get_by_role("button", name="Cancel").click()
    expect(panel).to_be_hidden()
    for i in range(3):
        expect(boxes.nth(i)).not_to_be_checked()


def test_merging_appends_onto_the_highest_step(signed_in: Page, recipe, add_step):
    """Merge posts only the checked steps (`hx-include`) and joins them onto the first."""
    for text in ("One.", "Two.", "Three."):
        add_step(recipe=recipe, text=text)
    steps = _open(signed_in, recipe)
    boxes = signed_in.locator(".step-select")

    boxes.nth(0).check()
    boxes.nth(2).check()
    signed_in.locator("#steps-panel").get_by_role("button", name="Merge").click()

    expect(steps).to_have_text(["One. Three.", "Two."])
    expect(signed_in.locator("#steps-panel")).to_be_hidden()
    assert _stored(recipe) == ["One. Three.", "Two."]


def test_bulk_delete_asks_first_and_removes_the_selection(signed_in: Page, recipe, add_step):
    """Delete confirms, then removes only the checked steps."""
    for text in ("One.", "Two.", "Three."):
        add_step(recipe=recipe, text=text)
    steps = _open(signed_in, recipe)
    boxes = signed_in.locator(".step-select")
    dialogs: list[str] = []

    def accept(dialog: Dialog) -> None:
        dialogs.append(dialog.message)
        dialog.accept()

    signed_in.on("dialog", accept)
    boxes.nth(0).check()
    boxes.nth(1).check()
    signed_in.locator("#steps-panel").get_by_role("button", name="Delete").click()

    expect(steps).to_have_text(["Three."])
    assert dialogs == ["Delete the selected steps?"]
    assert _stored(recipe) == ["Three."]
