"""The JSON API's examples are what its views send (#160, plan 012 M4).

`tests/api_examples/` holds one example of each request the recipe clipper
makes and the reply it gets. The extension's tests read the same files (M6), so
the two sides agree on the shape of every message. Each file is replayed here
against a small, fixed library, and the reply must match it exactly.
"""

import hashlib
import json
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from recipes.models import (
    ApiToken,
    Cuisine,
    Ingredient,
    IngredientAlias,
    Recipe,
    Tag,
    Unit,
    UnitAlias,
)

EXAMPLES = Path(__file__).resolve().parent.parent / "api_examples"
KEY = "nsh_example-key-for-the-api-examples"


def _example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text())


def _replay(example: dict):
    request = example["request"]
    headers = {k: v for k, v in request["headers"].items() if k != "Content-Type"}
    path, _, query = request["path"].partition("?")
    client = Client()
    if request["method"] == "GET":
        return client.get(path, QUERY_STRING=query, headers=headers)
    return client.post(
        path,
        json.dumps(request["body"]),
        content_type=request["headers"]["Content-Type"],
        QUERY_STRING=query,
        headers=headers,
    )


def _wipe_the_seeded_vocabulary() -> None:
    Ingredient.objects.all().delete()
    Unit.objects.all().delete()
    Tag.objects.all().delete()
    # A node's parent is PROTECT: take the leaves first.
    while Cuisine.objects.exists():
        Cuisine.objects.filter(children__isnull=True).delete()


@pytest.fixture
def cook(db) -> User:
    """The examples' user, with the key they send and a small library.

    Two global ingredients and a private one, two global units and a private
    one, two cuisines, a global tag and a private one.
    """
    _wipe_the_seeded_vocabulary()
    cook = User.objects.create_user(username="cook", password="x")
    ApiToken.objects.create(
        user=cook, name="examples", key_digest=hashlib.sha256(KEY.encode()).hexdigest()
    )
    aubergine = Ingredient.objects.create(ingredient_name="aubergine")
    IngredientAlias.objects.create(alias_name="eggplant", canonical=aubergine)
    Ingredient.objects.create(ingredient_name="basil")
    Ingredient.objects.create(ingredient_name="lemon", owner=cook)
    gram = Unit.objects.create(name="g", plural_name="g", dimension=Unit.MASS)
    UnitAlias.objects.create(alias_name="gram", unit=gram)
    tbsp = Unit.objects.create(name="tbsp", plural_name="tbsp", dimension=Unit.VOLUME)
    UnitAlias.objects.create(alias_name="tablespoon", unit=tbsp)
    Unit.objects.create(name="punnet", owner=cook)
    med = Cuisine.objects.create(cuisine="med")
    Cuisine.objects.create(cuisine="italy", parent=med)
    Tag.objects.create(tag="dinner")
    Tag.objects.create(tag="favourite", owner=cook)
    return cook


def _the_first_save() -> None:
    _replay(_example("save.json"))


def _someone_elses_recipe_with_the_saved_id() -> None:
    saved_id = _example("save.json")["response"]["body"]["recipes"][0]["id"]
    other = User.objects.create_user(username="other", password="x")
    Recipe.objects.create(pk=uuid.UUID(saved_id), recipe_name="Theirs", owner=other)


def _the_key_has_expired() -> None:
    ApiToken.objects.update(expires_at=timezone.now() - timedelta(days=1))


def _the_key_has_sent_its_requests_this_minute() -> None:
    for _ in range(settings.API_REQUESTS_PER_MINUTE):
        _replay(_example("vocabulary.json"))


# What each example assumes has happened before it.
GIVEN = {
    "save-again.json": _the_first_save,
    "save-id-taken.json": _someone_elses_recipe_with_the_saved_id,
    "vocabulary-key-expired.json": _the_key_has_expired,
    "vocabulary-too-many-requests.json": _the_key_has_sent_its_requests_this_minute,
}


def test_there_is_an_example_of_each_call():
    """Every reply the clipper must handle has an example."""
    assert sorted(p.name for p in EXAMPLES.glob("*.json")) == [
        "save-again.json",
        "save-id-taken.json",
        "save-not-json.json",
        "save-refused.json",
        "save.json",
        "vocabulary-key-expired.json",
        "vocabulary-too-many-requests.json",
        "vocabulary-without-key.json",
        "vocabulary.json",
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("*.json")))
@pytest.mark.usefixtures("cook")
def test_the_view_sends_what_the_example_shows(name: str):
    """Status, the headers the example names, and the body, exactly."""
    example = _example(name)
    if name in GIVEN:
        GIVEN[name]()

    response = _replay(example)

    expected = example["response"]
    assert response.status_code == expected["status"]
    for header, value in expected.get("headers", {}).items():
        assert response[header] == value
    assert response.json() == expected["body"]
