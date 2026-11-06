"""The clean-up tool's Alias action (plan 008, phase 5; #66)."""

import re

import pytest
from django.test import Client

from recipes.models import Ingredient, IngredientAlias, IngredientInRecipe

MANAGE = "/recipes/ingredients/manage/"
ALIAS = MANAGE + "alias/"
RECIPES = MANAGE + "recipes/"


@pytest.fixture
def staff_client(user):
    """The default user, made staff, logged in."""
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def aubergine(make_ingredient):
    """A global canonical ingredient."""
    return make_ingredient("aubergine")


def _button(html: str) -> str:
    match = re.search(r'<button[^>]*\bid="action-alias"[^>]*>', html)
    assert match is not None
    return match.group(0)


def _disabled(tag: str) -> bool:
    return re.search(r"\sdisabled(?=[\s>])", tag) is not None


@pytest.mark.django_db
def test_alias_button_needs_exactly_one_ingredient(staff_client, aubergine, make_ingredient):
    """Disabled with none or two selected, enabled with one."""
    other = make_ingredient("leek")
    assert _disabled(_button(staff_client.get(MANAGE).content.decode()))
    one = staff_client.get(RECIPES, {"ingredient_ids": [aubergine.pk]}).content.decode()
    assert not _disabled(_button(one))
    two = staff_client.get(RECIPES, {"ingredient_ids": [aubergine.pk, other.pk]}).content.decode()
    assert _disabled(_button(two))


@pytest.mark.django_db
def test_alias_panel_lists_the_current_aliases(staff_client, aubergine):
    """GET shows the selected ingredient's aliases and turns the button into Done."""
    IngredientAlias.objects.create(alias_name="eggplant", canonical=aubergine)
    IngredientAlias.objects.create(alias_name="brinjal", canonical=aubergine)
    response = staff_client.get(ALIAS, {"ingredient_ids": [aubergine.pk]})
    html = response.content.decode()
    assert response.status_code == 200
    assert html.index("brinjal") < html.index("eggplant")
    assert re.search(r'id="action-alias"[^>]*>\s*Done</button>', html)


@pytest.mark.django_db
@pytest.mark.parametrize("count", [0, 2])
def test_alias_needs_exactly_one_selected(staff_client, aubergine, make_ingredient, count):
    """The guard answers 422 for any other selection size."""
    ids = [aubergine.pk, make_ingredient("leek").pk][:count]
    response = staff_client.get(ALIAS, {"ingredient_ids": ids})
    assert response.status_code == 422
    assert "exactly 1 ingredient" in response.content.decode()


@pytest.mark.django_db
def test_adding_an_alias_persists_and_lists_it(staff_client, aubergine, user):
    """POST adds the alias and re-renders the panel with it."""
    response = staff_client.post(
        ALIAS, {"ingredient_ids": [aubergine.pk], "alias_name": "eggplant"}
    )
    assert response.status_code == 200
    assert "eggplant" in response.content.decode()
    assert IngredientAlias.objects.get().canonical == aubergine


@pytest.mark.django_db
def test_adding_an_alias_that_exists_as_a_row_reports_the_merge(
    staff_client, aubergine, make_ingredient, make_recipe, add_ingredient, user
):
    """Convergence: the old row's recipes move, and the panel says so."""
    eggplant = make_ingredient("eggplant")
    add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=eggplant)
    response = staff_client.post(
        ALIAS, {"ingredient_ids": [aubergine.pk], "alias_name": "eggplant"}
    )
    assert response.status_code == 200
    assert "merged 1 existing ingredient" in response.content.decode()
    assert IngredientInRecipe.objects.get().ingredient == aubergine
    assert not Ingredient.objects.filter(pk=eggplant.pk).exists()


@pytest.mark.django_db
def test_a_clashing_alias_answers_422_with_the_reason(staff_client, aubergine, make_ingredient):
    """An alias of another ingredient is refused, and the typed name kept."""
    IngredientAlias.objects.create(alias_name="eggplant", canonical=make_ingredient("brinjal"))
    response = staff_client.post(
        ALIAS, {"ingredient_ids": [aubergine.pk], "alias_name": "Eggplant"}
    )
    html = response.content.decode()
    assert response.status_code == 422
    assert "already an alias of “brinjal”" in html
    assert 'value="Eggplant"' in html


@pytest.mark.django_db
def test_a_private_ingredient_cannot_take_aliases(staff_client, user):
    """The panel says to promote first and offers no form."""
    private = Ingredient.objects.create(ingredient_name="yuzu", owner=user)
    html = staff_client.get(ALIAS, {"ingredient_ids": [private.pk]}).content.decode()
    assert "promote it first" in html
    assert 'name="alias_name"' not in html


@pytest.mark.django_db
def test_removing_an_alias_deletes_it(staff_client, aubergine):
    """POST with `remove_alias_id` forgets the mapping."""
    alias = IngredientAlias.objects.create(alias_name="eggplant", canonical=aubergine)
    response = staff_client.post(
        ALIAS, {"ingredient_ids": [aubergine.pk], "remove_alias_id": alias.pk}
    )
    assert response.status_code == 200
    assert not IngredientAlias.objects.exists()
    assert "eggplant" not in response.content.decode()


@pytest.mark.django_db
def test_removing_only_touches_the_selected_ingredients_aliases(
    staff_client, aubergine, make_ingredient
):
    """An alias id belonging to another ingredient is left alone."""
    theirs = IngredientAlias.objects.create(
        alias_name="courgette", canonical=make_ingredient("zucchini")
    )
    staff_client.post(ALIAS, {"ingredient_ids": [aubergine.pk], "remove_alias_id": theirs.pk})
    assert IngredientAlias.objects.filter(pk=theirs.pk).exists()


@pytest.mark.django_db
def test_alias_is_forbidden_to_non_staff_and_writes_nothing(other_user, aubergine):
    """Aliases are global and staff-defined (plan 011)."""
    client = Client()
    client.force_login(other_user)
    for response in (
        client.get(ALIAS, {"ingredient_ids": [aubergine.pk]}),
        client.post(ALIAS, {"ingredient_ids": [aubergine.pk], "alias_name": "eggplant"}),
    ):
        assert response.status_code == 403
    assert not IngredientAlias.objects.exists()
