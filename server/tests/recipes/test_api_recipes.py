"""Tests for the endpoint the recipe clipper submits recipes to (#78)."""

import json
import uuid

import pytest
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from recipes.models import Recipe
from recipes.services.api_tokens import create_token

URL = "/recipes/api/recipes/"
PANCAKES = {
    "@context": "https://schema.org",
    "@type": "Recipe",
    "name": "Pancakes",
    "url": "https://example.com/pancakes",
    "recipeYield": "4",
    "recipeIngredient": ["200 g flour", "2 eggs"],
    "recipeInstructions": "Mix.\nFry.",
}


@pytest.fixture
def key(user) -> str:
    """A key for `user`."""
    return create_token(user=user, name="clipper")[1]


def _post(body: object, *, key: str | None, client: Client | None = None, **extra):
    headers = {"Authorization": f"Bearer {key}"} if key is not None else {}
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return (client or Client()).post(
        URL, raw, content_type="application/json", headers=headers, **extra
    )


def test_route_name():
    """The extension's one address."""
    assert reverse("recipes:api_recipes") == URL


@pytest.mark.django_db
def test_submit_json_ld(user, key):
    """A scraped recipe is created for the key's user; the answer says where it is."""
    response = _post(PANCAKES, key=key)
    assert response.status_code == 201
    recipe = Recipe.objects.get(owner=user)
    assert recipe.recipe_name == "Pancakes"
    assert recipe.servings == 4
    assert recipe.source_instance == "https://example.com/pancakes"
    assert [s.step_text for s in recipe.steps.all()] == ["Mix.", "Fry."]
    assert response.json() == {
        "recipes": [
            {
                "id": str(recipe.pk),
                "name": "Pancakes",
                "url": f"http://testserver/recipes/{recipe.pk}/",
                "renamed": False,
                "in_trash": False,
            }
        ],
        "warnings": [],
    }


@pytest.mark.django_db
def test_submit_twice_renames(user, key):
    """Clipping the same page again keeps both, and says the second was renamed."""
    _post(PANCAKES, key=key)
    body = _post(PANCAKES, key=key).json()
    assert body["recipes"][0]["name"] == "Pancakes Imported"
    assert body["recipes"][0]["renamed"] is True


@pytest.mark.django_db
def test_submit_a_nutrisho_document(user, key):
    """The round-trip format is accepted too, warnings and all."""
    document = {
        "format": "nutrisho",
        "version": 1,
        "recipes": [{"recipe_name": "Soup", "cuisine": "atlantis"}],
    }
    body = _post(document, key=key).json()
    assert body["recipes"][0]["name"] == "Soup"
    assert body["warnings"] == ["“Soup”: there is no cuisine “atlantis” here, so it has none."]


@pytest.mark.django_db
def test_no_csrf_token_needed(user, key):
    """A client with no cookies has no CSRF token to send, and needs none."""
    client = Client(enforce_csrf_checks=True)
    assert _post(PANCAKES, key=key, client=client).status_code == 201


@pytest.mark.django_db
@pytest.mark.parametrize("auth", [None, "nsh_wrong", ""])
def test_refused_without_a_valid_key(user, auth: str | None):
    """No key, no recipe: 401 with a JSON reason and the scheme to use."""
    response = _post(PANCAKES, key=auth)
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == 'Bearer realm="nutrisho"'
    assert response.json() == {
        "error": "Send a valid API token as “Authorization: Bearer <token>”."
    }
    assert not Recipe.objects.exists()


@pytest.mark.django_db
def test_a_session_is_not_enough(user):
    """A signed-in browser session is not a key: the endpoint skips CSRF, so it must not use cookies."""
    client = Client()
    client.force_login(user)
    assert _post(PANCAKES, key=None, client=client).status_code == 401
    assert not Recipe.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"{nope", "This is not JSON"),
        (b"{}", "No recipe found"),
        (
            json.dumps({"format": "nutrisho", "version": 1, "recipes": [{}]}).encode(),
            "recipe_name is required",
        ),
    ],
)
def test_bad_body(key, body: bytes, message: str):
    """400 with the reason, and nothing written."""
    response = _post(body, key=key)
    assert response.status_code == 400
    assert message in response.json()["error"]
    assert not Recipe.objects.exists()


@pytest.mark.django_db
@override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=100)
def test_body_too_large(key):
    """413 for a body over Django's upload limit."""
    response = _post(PANCAKES | {"description": "x" * 200}, key=key)
    assert response.status_code == 413
    assert response.json() == {"error": "The request body is too large."}


@pytest.mark.django_db
def test_post_only(key):
    """Reading is not offered."""
    response = Client().get(URL, headers={"Authorization": f"Bearer {key}"})
    assert response.status_code == 405


@pytest.mark.django_db
def test_text_longer_than_its_column_is_refused(key):
    """A client cannot store more than a column holds."""
    document = {"format": "nutrisho", "version": 1, "recipes": [{"recipe_name": "x" * 201}]}
    response = _post(document, key=key)
    assert response.status_code == 400
    assert response.json() == {
        "error": "document.recipes[0].recipe_name must be at most 200 characters."
    }
    assert not Recipe.objects.exists()


# --- ?id=: a save names its recipe's id (#158) ----------------------------------


def _post_as(body: object, *, key: str, recipe_id: object):
    return _post(body, key=key, QUERY_STRING=f"id={recipe_id}")


@pytest.mark.django_db
def test_a_save_with_an_id_creates_the_recipe_under_it(user, key):
    """The clipper makes the id when its draft starts; the recipe is stored under it."""
    recipe_id = uuid.uuid7()
    response = _post_as(PANCAKES, key=key, recipe_id=recipe_id)
    assert response.status_code == 201
    recipe = Recipe.objects.get(owner=user)
    assert recipe.pk == recipe_id
    assert response.json()["recipes"][0]["id"] == str(recipe_id)
    assert response.json()["recipes"][0]["url"] == f"http://testserver/recipes/{recipe_id}/"


@pytest.mark.django_db
def test_the_same_save_twice_makes_one_recipe(user, key):
    """A save sent again writes nothing, and answers with the recipe the first one made."""
    recipe_id = uuid.uuid7()
    first = _post_as(PANCAKES, key=key, recipe_id=recipe_id).json()
    again = _post_as(PANCAKES | {"name": "Crêpes"}, key=key, recipe_id=recipe_id)
    assert again.status_code == 200
    assert again.json() == first
    assert list(Recipe.objects.values_list("recipe_name", flat=True)) == ["Pancakes"]


@pytest.mark.django_db
def test_a_save_whose_recipe_is_in_the_trash_answers_with_it(user, key):
    """A recipe deleted since its save is still the user's: it is not made again."""
    recipe_id = uuid.uuid7()
    _post_as(PANCAKES, key=key, recipe_id=recipe_id)
    Recipe.objects.filter(pk=recipe_id).update(deleted_at=timezone.now())
    response = _post_as(PANCAKES, key=key, recipe_id=recipe_id)
    assert response.status_code == 200
    assert response.json()["recipes"][0]["in_trash"] is True
    assert Recipe.objects.count() == 1


@pytest.mark.django_db
def test_someone_elses_id_is_refused_without_saying_whose(user, key, other_user):
    """409, a reason that names nobody, and nothing written."""
    theirs = Recipe.objects.create(recipe_name="Secret stew", owner=other_user)
    response = _post_as(PANCAKES, key=key, recipe_id=theirs.pk)
    assert response.status_code == 409
    assert response.json() == {"error": "That id is taken: make a new one for this recipe."}
    assert list(Recipe.objects.values_list("recipe_name", flat=True)) == ["Secret stew"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "recipe_id",
    ["10", "not-a-uuid", "", str(uuid.uuid4())],
    ids=["number", "text", "empty", "version-4"],
)
def test_an_id_that_is_not_a_version_7_uuid_is_refused(user, key, recipe_id: str):
    """400: new ids are version 7, so ordering by id stays ordering by age."""
    response = _post_as(PANCAKES, key=key, recipe_id=recipe_id)
    assert response.status_code == 400
    assert response.json() == {"error": "“id” must be a version 7 UUID."}
    assert not Recipe.objects.exists()


@pytest.mark.django_db
def test_an_id_names_one_recipe(user, key):
    """400 for a body that holds more than one recipe, and nothing written."""
    document = {
        "format": "nutrisho",
        "version": 1,
        "recipes": [{"recipe_name": "Soup"}, {"recipe_name": "Stew"}],
    }
    response = _post_as(document, key=key, recipe_id=uuid.uuid7())
    assert response.status_code == 400
    assert response.json() == {"error": "An id names one recipe, and this body holds 2."}
    assert not Recipe.objects.exists()
