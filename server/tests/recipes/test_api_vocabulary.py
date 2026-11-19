"""Tests for the lists the recipe clipper loads when its sidebar opens (#160, plan 012 M4)."""

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from recipes.models import Cuisine, Ingredient, IngredientAlias, Tag, Unit, UnitAlias
from recipes.services.api_tokens import create_token
from recipes.services.name_resolution import find_ingredient, find_unit
from recipes.services.recipe_document import FIELD_LENGTHS, ImportFormatError, parse_json

URL = "/recipes/api/vocabulary/"


@pytest.fixture
def key(user) -> str:
    """A key for `user`."""
    return create_token(user=user, name="clipper")[1]


def _get(*, key: str | None):
    headers = {"Authorization": f"Bearer {key}"} if key is not None else {}
    return Client().get(URL, headers=headers)


def _entry(body: dict, section: str, name: str) -> dict | None:
    return next((e for e in body[section] if e["name"] == name), None)


def _spellings(entries: list[dict], name: str) -> list[str]:
    entry = next(e for e in entries if e["name"] == name)
    return entry["spellings"]


def test_route_name():
    """The clipper's second address."""
    assert reverse("recipes:api_vocabulary") == URL


@pytest.mark.django_db
def test_the_sections(user, key):
    """Named sections, so a later kind of data is a new section rather than a new endpoint."""
    response = _get(key=key)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"user", "ingredients", "units", "cuisines", "tags", "limits"}
    assert body["user"] == user.get_username()


@pytest.mark.django_db
def test_an_ingredient_comes_with_every_spelling_the_server_accepts(user, key):
    """Its plural, its aliases and their plurals; the clipper never inflects a name itself."""
    aubergine = Ingredient.objects.create(ingredient_name="aubergine-v")
    IngredientAlias.objects.create(alias_name="eggplant-v", canonical=aubergine)
    Ingredient.objects.create(ingredient_name="mouse-v", plural_name="mice-v")
    Ingredient.objects.create(ingredient_name="v-oats")

    body = _get(key=key).json()

    assert _entry(body, "ingredients", "aubergine-v") == {
        "name": "aubergine-v",
        "spellings": ["aubergine-vs", "eggplant-v", "eggplant-vs"],
    }
    assert _entry(body, "ingredients", "mouse-v") == {"name": "mouse-v", "spellings": ["mice-v"]}
    # An ingredient whose plural is its name has no other spelling.
    assert _entry(body, "ingredients", "v-oats") == {"name": "v-oats", "spellings": []}
    for spelling in ["aubergine-vs", "eggplant-v", "eggplant-vs"]:
        assert find_ingredient(spelling, owner=user) == aubergine


@pytest.mark.django_db
def test_ingredients_are_the_global_ones_and_the_users_own(user, key, other_user):
    """Never another user's private ingredient."""
    Ingredient.objects.create(ingredient_name="mine-v", owner=user)
    Ingredient.objects.create(ingredient_name="theirs-v", owner=other_user)

    names = {e["name"] for e in _get(key=key).json()["ingredients"]}

    assert "mine-v" in names
    assert "theirs-v" not in names


@pytest.mark.django_db
def test_a_spelling_belongs_to_the_ingredient_the_server_resolves_it_to(user, key):
    """A name the user has globally and privately is listed once, as the global row.

    A spelling two rows could claim goes where `find_ingredient` sends it: a name
    before a plural, a plural before an alias.
    """
    Ingredient.objects.create(ingredient_name="Leek-v")
    Ingredient.objects.create(ingredient_name="leek-v", owner=user)
    Ingredient.objects.create(ingredient_name="pea-vs", owner=user)
    pea = Ingredient.objects.create(ingredient_name="pea-v")
    bean = Ingredient.objects.create(ingredient_name="bean-v")
    IngredientAlias.objects.create(alias_name="pea-vx", canonical=bean)
    Ingredient.objects.create(ingredient_name="pod-v", plural_name="pea-vx")

    ingredients = _get(key=key).json()["ingredients"]

    assert [e["name"] for e in ingredients if e["name"].lower() == "leek-v"] == ["Leek-v"]
    assert "pea-vs" not in _spellings(ingredients, "pea-v")
    assert find_ingredient("pea-vs", owner=user) != pea
    assert _spellings(ingredients, "pod-v") == ["pea-vx"]
    assert _spellings(ingredients, "bean-v") == ["bean-vs", "pea-vxes"]


@pytest.mark.django_db
def test_a_unit_comes_with_every_spelling_the_server_accepts(user, key, other_user):
    """The global units and the user's own, with plurals, aliases and their plurals."""
    tub = Unit.objects.create(name="tub-v", dimension=Unit.COUNT)
    UnitAlias.objects.create(alias_name="pot-v", unit=tub)
    Unit.objects.create(name="punnet-v", owner=user)
    Unit.objects.create(name="crate-v", owner=other_user)

    units = _get(key=key).json()["units"]

    assert _entry({"u": units}, "u", "tub-v") == {
        "name": "tub-v",
        "spellings": ["tub-vs", "pot-v", "pot-vs"],
    }
    assert _entry({"u": units}, "u", "punnet-v") == {"name": "punnet-v", "spellings": ["punnet-vs"]}
    assert _entry({"u": units}, "u", "crate-v") is None
    for spelling in ["tub-vs", "pot-v", "pot-vs"]:
        assert find_unit(spelling, owner=user) == tub


@pytest.mark.django_db
def test_every_seeded_unit_spelling_resolves_to_its_unit(user, key):
    """Checked against the server's own lookup over the whole seeded vocabulary."""
    for entry in _get(key=key).json()["units"]:
        unit = find_unit(entry["name"], owner=user)
        assert unit is not None
        for spelling in entry["spellings"]:
            assert find_unit(spelling, owner=user) == unit, spelling


@pytest.mark.django_db
def test_lists_are_sorted_ignoring_case(user, key):
    """Easy to read when debugging, and stable for a test to compare."""
    Ingredient.objects.create(ingredient_name="Zucchini-v")
    Ingredient.objects.create(ingredient_name="apple-v")
    body = _get(key=key).json()
    for section in ("ingredients", "units"):
        names = [e["name"] for e in body[section]]
        assert names == sorted(names, key=str.lower)
    assert body["tags"] == sorted(body["tags"], key=str.lower)


@pytest.mark.django_db
def test_tags_are_the_global_ones_and_the_users_own(user, key, other_user):
    """By name; a name the user has globally and privately is listed once."""
    Tag.objects.create(tag="Dinner-v")
    Tag.objects.create(tag="dinner-v", owner=user)
    Tag.objects.create(tag="favourite-v", owner=user)
    Tag.objects.create(tag="secret-v", owner=other_user)

    tags = [t for t in _get(key=key).json()["tags"] if t.endswith("-v")]

    assert tags == ["Dinner-v", "favourite-v"]


@pytest.mark.django_db
def test_cuisines_are_dotted_paths(user, key):
    """The tree, as the editor and a saved document name a node."""
    med = Cuisine.objects.create(cuisine="medi-v")
    Cuisine.objects.create(cuisine="italia-v", parent=med)
    cuisines = _get(key=key).json()["cuisines"]
    assert "medi-v" in cuisines
    assert "medi-v.italia-v" in cuisines


@pytest.mark.django_db
def test_limits_are_the_lengths_a_save_accepts(key):
    """The same numbers the reader enforces, so the clipper can flag a field before saving (D12)."""
    limits = _get(key=key).json()["limits"]
    assert limits == FIELD_LENGTHS
    assert limits["recipe_name"] == 200
    assert limits["step_text"] == 4000


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "place"),
    [
        ("recipe_name", lambda r, v: r | {"recipe_name": v}),
        ("short_description", lambda r, v: r | {"short_description": v}),
        ("source_instance", lambda r, v: r | {"source_instance": v}),
        ("cuisine", lambda r, v: r | {"cuisine": v}),
        ("tags", lambda r, v: r | {"tags": [v]}),
        ("step_title", lambda r, v: r | {"steps": [{"step_title": v, "step_text": "x"}]}),
        ("step_text", lambda r, v: r | {"steps": [{"step_text": v}]}),
        ("group_name", lambda r, v: r | {"ingredient_groups": [{"group_name": v}]}),
        *[
            (column, lambda r, v, column=column: r | _row({column: v}))
            for column in ("ingredient", "substitute", "unit", "legacy_unit", "preparation", "note")
        ],
    ],
)
def test_each_limit_is_where_the_reader_refuses(field: str, place):
    """A value at the limit is read, one character more is refused."""
    limit = FIELD_LENGTHS[field]
    recipe = {"recipe_name": "Soup"}

    parse_json(_document(place(recipe, "x" * limit)))
    with pytest.raises(ImportFormatError, match=f"at most {limit} characters"):
        parse_json(_document(place(recipe, "x" * (limit + 1))))


def _row(values: dict) -> dict:
    return {"ingredient_groups": [{"items": [{"ingredient": "salt"} | values]}]}


def _document(recipe: dict) -> bytes:
    import json

    return json.dumps({"format": "nutrisho", "version": 1, "recipes": [recipe]}).encode()


@pytest.mark.django_db
def test_the_number_of_queries_does_not_grow_with_the_library(user, key):
    """One read per kind of data, however many rows each holds."""

    def queries() -> int:
        with CaptureQueriesContext(connection) as captured:
            assert _get(key=key).status_code == 200
        return len(captured)

    before = queries()
    for n in range(5):
        ingredient = Ingredient.objects.create(ingredient_name=f"bulk-{n}-v")
        IngredientAlias.objects.create(alias_name=f"alias-{n}-v", canonical=ingredient)
        Ingredient.objects.create(ingredient_name=f"own-{n}-v", owner=user)
        unit = Unit.objects.create(name=f"unit-{n}-v", dimension=Unit.COUNT)
        UnitAlias.objects.create(alias_name=f"ualias-{n}-v", unit=unit)
        Tag.objects.create(tag=f"tag-{n}-v")
        Cuisine.objects.create(cuisine=f"area-{n}-v")
    assert queries() == before


@pytest.mark.django_db
@pytest.mark.parametrize("auth", [None, "nsh_wrong"])
def test_refused_without_a_valid_key(user, auth: str | None):
    """401 with a JSON reason and the scheme to use, as for a save."""
    response = _get(key=auth)
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == 'Bearer realm="nutrisho"'
    assert response.json() == {
        "error": "Send a valid API token as “Authorization: Bearer <token>”."
    }


@pytest.mark.django_db
def test_a_session_is_not_enough(user):
    """Like the save, it is signed in by a key only."""
    client = Client()
    client.force_login(user)
    assert client.get(URL).status_code == 401


@pytest.mark.django_db
def test_get_only(key):
    """Nothing is written here."""
    response = Client().post(URL, headers={"Authorization": f"Bearer {key}"})
    assert response.status_code == 405
