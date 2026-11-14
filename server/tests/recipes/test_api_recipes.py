"""Tests for the endpoint the recipe clipper submits recipes to (#78)."""

import json

import pytest
from django.test import Client, override_settings
from django.urls import reverse

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
                "id": recipe.pk,
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
