"""Tests for focus management and screen-reader announcements after HTMX swaps (#61).

The focus and announcement code runs in the browser; these tests pin the markup
it relies on (autofocus, stable ids, error attributes, the live region) and the
wiring in ``base.html``, the same way ``test_save_error_banner.py`` does for #37.
"""

import json
import re
from pathlib import Path

import pytest
from django.urls import reverse

from recipes.models import Cuisine, Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step

TEMPLATES = Path(__file__).resolve().parents[2] / "src" / "recipes" / "templates"


@pytest.fixture
def recipe(user) -> Recipe:
    """A recipe with one step and one ingredient in one group."""
    recipe = Recipe.objects.create(recipe_name="Soup", owner=user, servings=2)
    Step.objects.create(recipe=recipe, step_text="Boil water", index_in_sequence=0)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="Main", index_in_sequence=0)
    IngredientInRecipe.objects.create(
        ingredient=Ingredient.objects.create(ingredient_name="leek"),
        ingredient_group=group,
        index_in_sequence=0,
    )
    return recipe


@pytest.fixture
def step(recipe) -> Step:
    """The recipe's step."""
    return recipe.step.get()


@pytest.fixture
def group(recipe) -> IngredientGroup:
    """The recipe's ingredient group."""
    return recipe.ingredients_group.get()


@pytest.fixture
def iir(group) -> IngredientInRecipe:
    """The recipe's ingredient row."""
    return group.ingredient.get()


@pytest.fixture
def home_html(auth_client) -> str:
    """Rendered recipe list, which extends ``base.html``."""
    response = auth_client.get(reverse("recipes:home"))
    assert response.status_code == 200
    return response.content.decode()


def _get(client, name: str, **kwargs: object) -> str:
    response = client.get(reverse(f"recipes:{name}", kwargs=kwargs), HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    return response.content.decode()


def _tag(html: str, pattern: str) -> str:
    """The first opening tag matching ``pattern`` (a regex over the tag)."""
    match = re.search(rf"<[^>]*{pattern}[^>]*>", html)
    assert match, f"no tag matching {pattern!r}"
    return match.group(0)


def _announced(response) -> str:
    """The message a response asks the page to announce via ``HX-Trigger``."""
    return json.loads(response["HX-Trigger"])["announce"]["message"]


# --- the live region and the wiring in base.html ---------------------------


@pytest.mark.django_db
def test_status_region_is_a_persistent_polite_live_region(home_html):
    """One visually hidden region carries every polite announcement."""
    assert home_html.count('id="a11y-status"') == 1
    region = _tag(home_html, 'id="a11y-status"')
    assert 'role="status"' in region
    assert 'aria-live="polite"' in region
    assert "visually-hidden" in region
    assert " hidden" not in region, "a hidden live region announces nothing"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "wiring",
    [
        "'htmx:beforeSwap'",  # remembers where focus was
        "'htmx:afterRequest'",  # puts it back when the swap dropped it
        "'htmx:historyRestore'",  # back button, like a boosted page
        "'announce'",  # HX-Trigger from the delete views
        "[data-announce]",  # counts and "Saved" in swapped content
        '[aria-invalid="true"]',  # a 422 focuses the first invalid field
    ],
)
def test_base_wires_focus_and_announcements(home_html, wiring):
    """The global listeners for focus restore and announcements are on every page."""
    assert wiring in home_html


@pytest.mark.django_db
def test_visually_hidden_class_is_defined():
    """The live region is hidden visually, not from assistive tech."""
    css = (TEMPLATES.parent / "static" / "css" / "style.css").read_text()
    assert ".visually-hidden" in css


# --- autofocus on the first field of every inline form ---------------------


@pytest.mark.django_db
@pytest.mark.parametrize("field_name", ["recipe_name", "short_description", "servings"])
def test_field_edit_autofocuses_its_input(auth_client, recipe, field_name):
    """Clicking a field to edit it puts the cursor in the field."""
    html = _get(auth_client, "field_edit", recipe_id=recipe.pk, field_name=field_name)
    assert "autofocus" in _tag(html, f'name="{field_name}"')


@pytest.mark.django_db
def test_step_edit_autofocuses_the_title(auth_client, recipe, step):
    """The step form's first field is the title."""
    html = _get(auth_client, "step_edit", recipe_id=recipe.pk, step_id=step.pk)
    assert "autofocus" in _tag(html, 'name="step_title"')
    assert "autofocus" not in _tag(html, 'name="step_text"')


@pytest.mark.django_db
def test_new_step_form_autofocuses_the_title(auth_client, recipe):
    """+ Add step opens a form with the cursor already in it."""
    response = auth_client.post(reverse("recipes:step_add", kwargs={"recipe_id": recipe.pk}))
    assert "autofocus" in _tag(response.content.decode(), 'name="step_title"')


@pytest.mark.django_db
def test_ingredient_edit_autofocuses_the_quantity(auth_client, recipe, iir):
    """The ingredient form's first field is the quantity."""
    html = _get(auth_client, "ingredient_edit", recipe_id=recipe.pk, iir_id=iir.pk)
    assert "autofocus" in _tag(html, 'name="quantity"')
    assert "autofocus" not in _tag(html, 'name="ingredient_name"')


@pytest.mark.django_db
def test_group_edit_autofocuses_the_name(auth_client, recipe, group):
    """The group form has one field."""
    html = _get(auth_client, "group_edit", recipe_id=recipe.pk, group_id=group.pk)
    assert "autofocus" in _tag(html, 'name="group_name"')


@pytest.mark.django_db
def test_metadata_panel_autofocuses_the_first_field(auth_client, recipe):
    """The panel is injected above its trigger, so focus has to be moved into it."""
    html = _get(auth_client, "metadata_edit", recipe_id=recipe.pk)
    assert "autofocus" in _tag(html, 'name="recipe_name"')
    assert html.count("autofocus") == 1


@pytest.mark.django_db
def test_scale_panel_autofocuses_the_servings(auth_client, recipe):
    """The scale panel opens with the cursor in the servings field."""
    html = _get(auth_client, "scale_panel", recipe_id=recipe.pk)
    assert "autofocus" in _tag(html, 'name="servings"')


@pytest.mark.django_db
def test_delete_panel_autofocuses_cancel(auth_client, recipe):
    """The safe choice gets focus, so a stray Enter does not delete the recipe."""
    html = _get(auth_client, "delete_panel", recipe_id=recipe.pk)
    cancel = re.search(r"<button[^>]*>\s*Cancel\s*</button>", html)
    assert cancel
    assert "autofocus" in cancel.group(0)


# --- stable ids on move buttons, so htmx refocuses them --------------------


@pytest.mark.django_db
def test_move_buttons_have_stable_ids(auth_client, recipe, step, group, iir):
    """The ids let htmx refocus a move button after the list is re-rendered."""
    html = auth_client.get(recipe.get_absolute_url()).content.decode()
    for prefix in (f"step-{step.pk}", f"iir-{iir.pk}", f"group-{group.pk}"):
        assert f'id="{prefix}-up"' in html
        assert f'id="{prefix}-down"' in html


@pytest.mark.django_db
def test_step_move_keeps_the_button_ids(auth_client, recipe, step):
    """The re-rendered list carries the same ids, so focus stays on the button."""
    response = auth_client.post(
        reverse("recipes:step_move_up", kwargs={"recipe_id": recipe.pk, "step_id": step.pk})
    )
    assert f'id="step-{step.pk}-up"' in response.content.decode()


# --- panels: cancel returns focus to the toggle ----------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("panel", ["metadata-panel", "scale-panel", "delete-panel"])
def test_panel_toggles_name_their_panel(auth_client, recipe, panel):
    """Closing a panel sends focus back to the toggle that names it."""
    html = auth_client.get(recipe.get_absolute_url()).content.decode()
    assert f'aria-controls="{panel}"' in html


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "panel"),
    [
        ("metadata_edit", "metadata-panel"),
        ("scale_panel", "scale-panel"),
        ("delete_panel", "delete-panel"),
    ],
)
def test_panel_cancel_returns_focus(auth_client, recipe, name, panel):
    """Cancel closes the panel through the helper that refocuses the toggle."""
    html = _get(auth_client, name, recipe_id=recipe.pk)
    assert f"_closePanel('{panel}')" in html
    assert "innerHTML=''" not in html.replace(" ", "")


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["step_add", "group_add"])
def test_draft_cancel_moves_focus_to_a_neighbour(auth_client, recipe, name):
    """Cancelling an unsaved draft does not drop focus to <body>."""
    response = auth_client.post(reverse(f"recipes:{name}", kwargs={"recipe_id": recipe.pk}))
    html = response.content.decode()
    assert "_cancelDraft(this" in html
    assert ".remove()" not in html


@pytest.mark.django_db
def test_ingredient_draft_cancel_moves_focus_to_a_neighbour(auth_client, recipe, group):
    """Same for an unsaved ingredient row."""
    response = auth_client.post(
        reverse(
            "recipes:ingredient_add_to_group",
            kwargs={"recipe_id": recipe.pk, "group_id": group.pk},
        )
    )
    html = response.content.decode()
    assert "_cancelDraft(this" in html
    assert ".remove()" not in html


# --- boosted navigation lands on the page heading --------------------------


@pytest.mark.django_db
def test_page_headings_are_focusable(auth_client, recipe):
    """After a boosted swap focus moves to the page's <h1>."""
    for url in (
        reverse("recipes:home"),
        reverse("recipes:new"),
        reverse("recipes:metadata_edit", kwargs={"recipe_id": recipe.pk}),
    ):
        heading = re.search(r"<h1\b[^>]*>", auth_client.get(url).content.decode())
        assert heading, url
        assert 'tabindex="-1"' in heading.group(0), url


# --- error messages and invalid fields -------------------------------------


def test_every_form_error_is_an_alert():
    """Each 422 message is read out as soon as it appears."""
    for path in TEMPLATES.rglob("*.html"):
        for tag in re.findall(r'<[^>]*class="form-error"[^>]*>', path.read_text()):
            assert 'role="alert"' in tag, f"{path.name}: {tag}"


@pytest.mark.django_db
def test_ingredient_name_error_marks_the_input(auth_client, recipe, iir):
    """The hand-rendered ingredient input points at its error, like Django's own."""
    response = auth_client.post(
        reverse("recipes:ingredient_save", kwargs={"recipe_id": recipe.pk, "iir_id": iir.pk}),
        {"ingredient_name": ""},
    )
    html = response.content.decode()
    tag = _tag(html, 'name="ingredient_name"')
    assert 'aria-invalid="true"' in tag
    assert 'aria-describedby="id_ingredient_name_error"' in tag
    assert 'id="id_ingredient_name_error"' in html


@pytest.mark.django_db
def test_valid_ingredient_name_is_not_marked(auth_client, recipe, iir):
    """No error, no aria-invalid."""
    html = _get(auth_client, "ingredient_edit", recipe_id=recipe.pk, iir_id=iir.pk)
    assert "aria-invalid" not in _tag(html, 'name="ingredient_name"')


@pytest.mark.django_db
@pytest.mark.parametrize("panel", [True, False])
def test_cuisine_name_error_marks_the_input(auth_client, recipe, panel):
    """Same for the hand-rendered cuisine input, in the panel and on the full page."""
    headers = {"HTTP_HX_REQUEST": "true"} if panel else {}
    response = auth_client.post(
        reverse("recipes:metadata_edit", kwargs={"recipe_id": recipe.pk}),
        {"recipe_name": "Soup", "servings": 2, "cuisine_name": "atlantis"},
        **headers,
    )
    html = response.content.decode()
    tag = _tag(html, 'name="cuisine_name"')
    assert 'aria-invalid="true"' in tag
    assert 'aria-describedby="id_cuisine_name_error"' in tag
    assert 'id="id_cuisine_name_error"' in html


@pytest.mark.django_db
def test_new_recipe_cuisine_error_marks_the_input(auth_client):
    """The new-recipe page renders the cuisine input by hand too."""
    response = auth_client.post(
        reverse("recipes:new"),
        {"recipe_name": "Stew", "servings": 2, "cuisine_name": "atlantis"},
    )
    tag = _tag(response.content.decode(), 'name="cuisine_name"')
    assert 'aria-invalid="true"' in tag
    assert 'aria-describedby="id_cuisine_name_error"' in tag


# --- deletions are announced -----------------------------------------------


@pytest.mark.django_db
def test_step_delete_is_announced(auth_client, recipe, step):
    """A deleted row just vanishes, so the response says what happened."""
    response = auth_client.post(
        reverse("recipes:step_delete", kwargs={"recipe_id": recipe.pk, "step_id": step.pk})
    )
    assert _announced(response) == "Step deleted."


@pytest.mark.django_db
def test_steps_bulk_delete_is_announced(auth_client, recipe, step):
    """The count is in the message."""
    response = auth_client.post(
        reverse("recipes:steps_bulk_delete", kwargs={"recipe_id": recipe.pk}),
        {"step_ids": [step.pk]},
    )
    assert response.status_code == 200
    assert _announced(response) == "1 step deleted."


@pytest.mark.django_db
def test_ingredient_delete_is_announced(auth_client, recipe, iir):
    """Ingredient rows too, including the one that prunes its group."""
    response = auth_client.post(
        reverse("recipes:ingredient_delete", kwargs={"recipe_id": recipe.pk, "iir_id": iir.pk})
    )
    assert _announced(response) == "Ingredient deleted."


@pytest.mark.django_db
def test_group_delete_is_announced(auth_client, recipe, group):
    """And groups."""
    response = auth_client.post(
        reverse("recipes:group_delete", kwargs={"recipe_id": recipe.pk, "group_id": group.pk})
    )
    assert _announced(response) == "Group deleted."


@pytest.mark.django_db
def test_recipe_delete_from_the_list_is_announced(auth_client, user, recipe):
    """Deleting a row of the recipe list says so."""
    Recipe.objects.create(recipe_name="Stew", owner=user)
    response = auth_client.post(
        reverse("recipes:delete", kwargs={"recipe_id": recipe.pk}),
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET=f"recipe-{recipe.pk}",
    )
    assert _announced(response) == "Recipe deleted."


# --- counts and "Saved" in the clean-up tools ------------------------------


@pytest.fixture
def staff_client(auth_client, user):
    """The default client, made staff for the clean-up tools."""
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return auth_client


@pytest.mark.django_db
def test_ingredient_tool_counts_are_announced(staff_client):
    """Found/selected counts change on every click or keystroke."""
    Ingredient.objects.create(ingredient_name="leek")
    html = staff_client.get(reverse("recipes:ingredient_manage")).content.decode()
    assert "data-announce" in _tag(html, r'class="column-count[^"]*"[^>]*')
    assert html.count(" data-announce>") == 2  # column 2 and column 3


@pytest.mark.django_db
def test_ingredient_tool_saved_is_announced(staff_client):
    """'Saved' appears in a panel that was just swapped in."""
    onion = Ingredient.objects.create(ingredient_name="onion")
    carrot = Ingredient.objects.create(ingredient_name="carrot")
    response = staff_client.post(
        reverse("recipes:ingredient_manage_save", kwargs={"ingredient_id": onion.pk}),
        {"ingredient_name": "spring onion", "ingredient_ids": [onion.pk, carrot.pk]},
    )
    assert "data-announce" in _tag(response.content.decode(), 'class="panel-saved')


@pytest.mark.django_db
def test_cuisine_tool_counts_are_announced_and_checkboxes_have_ids(staff_client):
    """A checkbox click re-renders both columns; the id keeps focus on the box."""
    node = Cuisine.objects.create(cuisine="atlantis")
    html = staff_client.get(reverse("recipes:cuisine_manage")).content.decode()
    assert html.count(" data-announce>") == 2
    assert f'id="cuisine-pick-{node.pk}"' in html


@pytest.mark.django_db
def test_boosted_recipe_page_keeps_the_page_regions(auth_client, recipe):
    """A boosted visit swaps in a partial for the whole <body>, so it brings them back."""
    html = auth_client.get(
        recipe.get_absolute_url(), HTTP_HX_REQUEST="true", HTTP_HX_BOOSTED="true"
    ).content.decode()
    assert "<body" not in html
    assert html.count('id="a11y-status"') == 1
    assert html.count('id="save-error"') == 1


@pytest.mark.django_db
def test_full_recipe_page_has_the_page_regions_once(auth_client, recipe):
    """The full page gets them from base.html only."""
    html = auth_client.get(recipe.get_absolute_url()).content.decode()
    assert html.count('id="a11y-status"') == 1
    assert html.count('id="save-error"') == 1
