"""Tests for the recipe page's read (cook) mode and its Edit toggle (#58, #60).

A recipe opens to be read: a tap on a line, as when scrolling on a kitchen
tablet, must not open an editor. Editing is a mode the user asks for, and in it
every line is a real button, so the keyboard can start an edit too.
"""

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from recipes.models import Ingredient, Recipe, Step

STYLE_CSS = Path(__file__).resolve().parents[2] / "src" / "recipes" / "static" / "css" / "style.css"
TEMPLATES = Path(__file__).resolve().parents[2] / "src" / "recipes" / "templates" / "recipes"

EDIT_CONTROLS = (
    'class="btn-add"',
    'class="step-select"',
    'class="ingredient-select"',
    'class="move-btns"',
    'id="steps-panel"',
    'id="reassign-panel"',
    "hx-get=",
)


@pytest.fixture
def recipe(
    user: User,
    make_ingredient: Callable[..., Ingredient],
    add_ingredient: Callable[..., object],
    add_step: Callable[..., object],
) -> Recipe:
    """A recipe with a step and an ingredient, so every kind of line shows."""
    recipe = Recipe.objects.create(recipe_name="Leek Soup", owner=user, servings=2)
    add_step(recipe=recipe, text="Sweat the <b>leeks</b>.", title="Leeks")
    add_ingredient(recipe=recipe, ingredient=make_ingredient(name="leek"), quantity=2)
    return recipe


def _page(client: Client, url: str) -> str:
    response = client.get(url)
    assert response.status_code == 200
    return response.content.decode()


def _sheet(html: str) -> str:
    match = re.search(r'<main class="recipe-contents".*?</main>', html, flags=re.DOTALL)
    assert match, "recipe sheet missing"
    return match.group(0)


def _edit_url(recipe: Recipe) -> str:
    return recipe.get_absolute_url() + "?edit=1"


@pytest.mark.django_db
class TestReadMode:
    """The page as it opens: the recipe and nothing that edits it."""

    def test_shows_the_recipe(self, auth_client: Client, recipe: Recipe):
        """The title, steps, ingredients and group names are all there to read."""
        sheet = _sheet(_page(auth_client, recipe.get_absolute_url()))

        assert "Leek Soup" in sheet
        assert "Sweat the <b>leeks</b>." in sheet
        assert re.search(r'class="ingredient-name">\s*leeks\s*<', sheet)
        assert re.search(r'class="group-name">\s*Main\s*<', sheet)

    @pytest.mark.parametrize("control", EDIT_CONTROLS)
    def test_has_no_editing_controls(self, auth_client: Client, recipe: Recipe, control: str):
        """No editor trigger, tick box, move button, add button or panel."""
        assert control not in _sheet(_page(auth_client, recipe.get_absolute_url()))

    def test_has_no_edit_buttons(self, auth_client: Client, recipe: Recipe):
        """Nothing on the sheet is a button, so nothing there reacts to a tap."""
        assert "<button" not in _sheet(_page(auth_client, recipe.get_absolute_url()))

    def test_leaves_out_an_empty_blurb(self, auth_client: Client, recipe: Recipe):
        """A placeholder dash is something to click in edit mode, not to read."""
        assert "—" not in _sheet(_page(auth_client, recipe.get_absolute_url()))

    def test_offers_the_edit_toggle(self, auth_client: Client, recipe: Recipe):
        """Edit recipe, in the margin, opens the same page in edit mode."""
        html = _page(auth_client, recipe.get_absolute_url())

        assert re.search(rf'<a href="{re.escape(_edit_url(recipe))}"[^>]*>Edit recipe</a>', html)

    def test_scaled_page_is_read_only_too(self, auth_client: Client, recipe: Recipe):
        """Other servings are for reading as well."""
        sheet = _sheet(_page(auth_client, recipe.get_absolute_url() + "?servings=4"))

        assert "hx-get=" not in sheet
        assert "Serves 4" in sheet

    def test_boosted_visit_opens_in_read_mode(self, auth_client: Client, recipe: Recipe):
        """Previous and next arrive in read mode."""
        html = auth_client.get(
            recipe.get_absolute_url(), HTTP_HX_REQUEST="true", HTTP_HX_BOOSTED="true"
        ).content.decode()

        assert "hx-get=" not in _sheet(html)


@pytest.mark.django_db
class TestEditMode:
    """?edit=1: every line is a button that opens its editor."""

    def test_lines_are_buttons_that_open_their_editor(self, auth_client: Client, recipe: Recipe):
        """The title, a step, a group name and an ingredient each open their editor."""
        sheet = _sheet(_page(auth_client, _edit_url(recipe)))
        step = Step.objects.get(recipe=recipe)

        assert re.search(
            r'<button\s+type="button"\s+class="editable step-content"\s+'
            rf'hx-get="{reverse("recipes:step_edit", args=[recipe.id, step.id])}"',
            sheet,
        )
        title_edit = reverse("recipes:field_edit", args=[recipe.id, "recipe_name"])
        assert re.search(rf'<button\s+type="button"\s+hx-get="{title_edit}"', sheet)
        assert re.search(r'<h3 class="group-name">\s*<button\s+type="button"', sheet)
        assert re.search(r'<button\s+type="button"\s+class="editable ingredient-content"', sheet)

    @pytest.mark.parametrize("control", EDIT_CONTROLS)
    def test_has_the_editing_controls(self, auth_client: Client, recipe: Recipe, control: str):
        """Every control read mode leaves out is back."""
        assert control in _sheet(_page(auth_client, _edit_url(recipe)))

    def test_shows_a_dash_to_click_for_an_empty_blurb(self, auth_client: Client, recipe: Recipe):
        """An empty blurb still has something to click."""
        assert "—" in _sheet(_page(auth_client, _edit_url(recipe)))

    def test_offers_the_way_back_to_reading(self, auth_client: Client, recipe: Recipe):
        """Done editing returns to the plain page."""
        html = _page(auth_client, _edit_url(recipe))

        assert re.search(
            rf'<a href="{re.escape(recipe.get_absolute_url())}"[^>]*>Done editing</a>', html
        )
        assert "Edit recipe</a>" not in html

    def test_edit_tools_live_in_edit_mode_only(self, auth_client: Client, recipe: Recipe):
        """Edit details is editing too; Scale, Duplicate and Delete serve both modes."""
        details = reverse("recipes:metadata_edit", args=[recipe.id])

        assert details not in _page(auth_client, recipe.get_absolute_url())
        assert details in _page(auth_client, _edit_url(recipe))

    def test_saved_line_comes_back_as_a_button(self, auth_client: Client, recipe: Recipe):
        """A partial endpoint is only reached while editing, so it renders the button."""
        step = Step.objects.get(recipe=recipe)
        html = auth_client.get(
            reverse("recipes:step_display", args=[recipe.id, step.id]), HTTP_HX_REQUEST="true"
        ).content.decode()

        assert re.search(r'<button\s+type="button"\s+class="editable step-content"', html)


@pytest.mark.django_db
class TestArrivingInEditMode:
    """A recipe just made, or just copied, is there to be filled in."""

    def test_new_recipe_opens_in_edit_mode(self, auth_client: Client, user: User):
        """A new recipe is empty, so it opens ready for its steps."""
        response = auth_client.post(reverse("recipes:new"), {"recipe_name": "Fresh", "servings": 2})
        recipe = Recipe.objects.get(recipe_name="Fresh", owner=user)

        assert response.headers["Location"] == _edit_url(recipe)

    def test_duplicate_opens_in_edit_mode(self, auth_client: Client, recipe: Recipe):
        """A copy is made to be changed."""
        response = auth_client.post(reverse("recipes:duplicate", args=[recipe.id]))
        copy = Recipe.objects.exclude(pk=recipe.pk).get()

        assert response.headers["Location"] == _edit_url(copy)


@pytest.mark.parametrize(
    "template",
    [
        "partials/_field_edit.html",
        "partials/_step_edit.html",
        "partials/_ingredient_edit.html",
        "partials/_group_edit.html",
    ],
)
def test_escape_cancels_every_inline_editor(template: str):
    """Each editor's Cancel is marked so app.js can press it on Escape."""
    html = (TEMPLATES / template).read_text()

    assert re.search(r"<button[^>]*data-escape[^>]*>\s*Cancel</button>", html, flags=re.DOTALL)


def test_app_js_presses_cancel_on_escape(app_js: str):
    """The Escape listener looks for the marked Cancel."""
    assert "'Escape'" in app_js
    assert "[data-escape]" in app_js


def test_type_is_set_in_rem():
    """The browser's font-size setting reaches every page, the sheet included."""
    css = STYLE_CSS.read_text()

    assert re.findall(r"(?:font|font-size|line-height):[^;]*\d+px", css) == []
