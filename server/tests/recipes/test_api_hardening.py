"""The JSON API, hardened for the recipe clipper (#149, plan 012 M10).

An expired key has a reply of its own, so the clipper can say to make a new
one; a body that is not JSON is a 415; too many requests are a 429 with
`Retry-After`; and one request may bring only so many recipes and so many
names the user has not got yet.
"""

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from recipes.models import ApiToken, Ingredient, Recipe, Tag
from recipes.services.api_limits import new_name_count
from recipes.services.api_tokens import TokenExpiredError, create_token, user_for_key
from recipes.services.recipe_document import parse_document

SAVE = "/recipes/api/recipes/"
LISTS = "/recipes/api/vocabulary/"
SOUP = {"format": "nutrisho", "version": 1, "recipes": [{"recipe_name": "Soup"}]}


@pytest.fixture
def key(user) -> str:
    """A key for `user`."""
    return create_token(user=user, name="clipper")[1]


def _post(body: object, *, key: str | None, content_type: str = "application/json", **extra):
    headers = {"Authorization": f"Bearer {key}"} if key is not None else {}
    return Client().post(
        SAVE, json.dumps(body), content_type=content_type, headers=headers, **extra
    )


def _get(*, key: str | None, **extra):
    headers = {"Authorization": f"Bearer {key}"} if key is not None else {}
    return Client().get(LISTS, headers=headers, **extra)


def _age(token: ApiToken, *, days: int, used: bool = True) -> None:
    then = timezone.now() - timedelta(days=days)
    ApiToken.objects.filter(pk=token.pk).update(
        created_at=then, last_used_at=then if used else None
    )


# --- Expiry ----------------------------------------------------------------------


@pytest.mark.django_db
def test_a_key_can_be_made_to_expire_on_a_date(user):
    """`days` sets `expires_at`; none means it never does."""
    lasting, _ = create_token(user=user)
    dated, _ = create_token(user=user, days=30)
    assert lasting.expires_at is None
    assert dated.expires_at is not None
    assert timedelta(days=29) < dated.expires_at - timezone.now() <= timedelta(days=30)


@pytest.mark.django_db
def test_a_key_past_its_date_has_expired(user):
    """Its user is not signed in, and the error says why."""
    token, key = create_token(user=user, days=1)
    ApiToken.objects.filter(pk=token.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(TokenExpiredError):
        user_for_key(key)


@pytest.mark.django_db
def test_a_key_left_unused_too_long_has_expired(user, settings):
    """Idle days count from the last use, or from when it was made if never used."""
    settings.API_TOKEN_IDLE_DAYS = 90
    used, used_key = create_token(user=user)
    unused, unused_key = create_token(user=user)
    _age(used, days=91)
    _age(unused, days=91, used=False)
    with pytest.raises(TokenExpiredError):
        user_for_key(used_key)
    with pytest.raises(TokenExpiredError):
        user_for_key(unused_key)


@pytest.mark.django_db
def test_a_key_used_recently_has_not_expired(user, settings):
    """Each use starts the idle days again."""
    settings.API_TOKEN_IDLE_DAYS = 90
    token, key = create_token(user=user)
    _age(token, days=89)
    assert user_for_key(key) == user


@pytest.mark.django_db
@pytest.mark.parametrize("days", [0, None])
def test_idle_expiry_can_be_turned_off(user, settings, days):
    """0 or blank keeps an idle key working."""
    settings.API_TOKEN_IDLE_DAYS = days
    token, key = create_token(user=user)
    _age(token, days=3650)
    assert user_for_key(key) == user


@pytest.mark.django_db
def test_an_expired_key_gets_a_reply_of_its_own(user):
    """Still a 401, but with `token_expired`, so the clipper says to make a new key."""
    token, key = create_token(user=user, days=1)
    ApiToken.objects.filter(pk=token.pk).update(expires_at=timezone.now() - timedelta(days=1))
    for response in (_post(SOUP, key=key), _get(key=key)):
        assert response.status_code == 401
        assert response.json() == {
            "error": "This API token has expired: make a new one.",
            "code": "token_expired",
        }
        assert response["WWW-Authenticate"] == (
            'Bearer realm="nutrisho", error="invalid_token", '
            'error_description="The token has expired"'
        )
    assert not Recipe.objects.exists()


@pytest.mark.django_db
def test_an_unknown_key_keeps_its_plain_reply(user):
    """Nothing says whether a wrong key was ever a key."""
    response = _post(SOUP, key="nsh_wrong")
    assert response.status_code == 401
    assert "code" not in response.json()
    assert response["WWW-Authenticate"] == 'Bearer realm="nutrisho"'


@pytest.mark.django_db
def test_the_command_makes_a_key_that_expires(user):
    """`create_api_token --days 30` sets the date."""
    out = StringIO()
    call_command("create_api_token", "gotofritz", "--days", "30", stdout=out)
    assert ApiToken.objects.get(user=user).expires_at is not None
    assert "expires" in out.getvalue()


@pytest.mark.django_db
def test_the_admin_shows_when_a_key_expires():
    """Both limits are easy to see, so an expired key is easy to spot and delete."""
    from django.contrib import admin

    model_admin = admin.site._registry[ApiToken]
    assert "expires_at" in model_admin.list_display
    assert "expired" in model_admin.list_display


# --- Content type ------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded"])
def test_a_body_that_is_not_json_is_refused(user, key, content_type):
    """415, and nothing is written."""
    response = _post(SOUP, key=key, content_type=content_type)
    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_media_type"
    assert not Recipe.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "content_type", ["application/json", "application/ld+json", "application/json; charset=utf-8"]
)
def test_json_is_taken(user, key, content_type):
    """JSON and JSON-LD, with or without a charset."""
    assert _post(SOUP, key=key, content_type=content_type).status_code == 201


# --- Rate limits ---------------------------------------------------------------------


@pytest.mark.django_db
def test_too_many_requests_from_one_key_wait(user, key, settings):
    """Past the key's requests a minute, a 429 says how long to wait."""
    settings.API_REQUESTS_PER_MINUTE = 2
    assert _get(key=key).status_code == 200
    assert _get(key=key).status_code == 200
    response = _post(SOUP, key=key)
    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert 0 < int(response["Retry-After"]) <= 60
    assert not Recipe.objects.exists()


@pytest.mark.django_db
def test_another_key_is_counted_apart(user, other_user, key, settings):
    """One busy client does not hold up another."""
    settings.API_REQUESTS_PER_MINUTE = 1
    _get(key=key)
    other_key = create_token(user=other_user)[1]
    assert _get(key=other_key).status_code == 200


@pytest.mark.django_db
def test_too_many_wrong_keys_from_one_address_wait(user, key, settings):
    """Failed sign-ins are counted by address; past the limit even a right key waits."""
    settings.API_FAILED_KEYS_PER_MINUTE = 2
    assert _get(key="nsh_wrong").status_code == 401
    assert _get(key="nsh_wrong").status_code == 401
    response = _get(key=key)
    assert response.status_code == 429
    assert "Retry-After" in response
    assert _get(key=key, REMOTE_ADDR="10.0.0.9").status_code == 200


@pytest.mark.django_db
def test_the_count_starts_again_after_a_minute(user, key, settings, monkeypatch):
    """The window is a minute from the first request in it."""
    settings.API_REQUESTS_PER_MINUTE = 1
    now = timezone.now().timestamp()
    monkeypatch.setattr("recipes.services.api_limits._now", lambda: now)
    assert _get(key=key).status_code == 200
    assert _get(key=key).status_code == 429
    monkeypatch.setattr("recipes.services.api_limits._now", lambda: now + 61)
    assert _get(key=key).status_code == 200


# --- Caps on one request ---------------------------------------------------------------


@pytest.mark.django_db
def test_too_many_recipes_in_one_request_are_refused(user, key, settings):
    """413, naming the cap, and nothing is written."""
    settings.API_MAX_RECIPES = 2
    body = {
        "format": "nutrisho",
        "version": 1,
        "recipes": [{"recipe_name": f"Soup {n}"} for n in range(3)],
    }
    response = _post(body, key=key)
    assert response.status_code == 413
    assert response.json() == {
        "error": "One request may bring at most 2 recipes; this one has 3.",
        "code": "too_many_recipes",
    }
    assert not Recipe.objects.exists()


def _with_ingredients(*names: str, tags: tuple[str, ...] = ()) -> dict:
    items = [{"ingredient": name, "unit": "g"} for name in names]
    recipe = {"recipe_name": "Soup", "tags": list(tags), "ingredient_groups": [{"items": items}]}
    return {"format": "nutrisho", "version": 1, "recipes": [recipe]}


@pytest.mark.django_db
def test_too_many_new_names_in_one_request_are_refused(user, key, settings):
    """A request may not flood the user's suggestions with names; nothing is written."""
    settings.API_MAX_NEW_NAMES = 3
    before = (Ingredient.objects.count(), Tag.objects.count())
    response = _post(_with_ingredients("zibibbo", "cardoon", tags=("odd", "rare")), key=key)
    assert response.status_code == 413
    assert response.json() == {
        "error": "One request may make at most 3 new names; this one would make 4.",
        "code": "too_many_new_names",
    }
    assert (Ingredient.objects.count(), Tag.objects.count()) == before
    assert not Recipe.objects.exists()


@pytest.mark.django_db
def test_names_the_user_has_are_not_new(user, key, settings):
    """Known names, by any spelling, and repeats count for nothing."""
    settings.API_MAX_NEW_NAMES = 1
    Ingredient.objects.create(ingredient_name="cardoon", owner=user)
    response = _post(_with_ingredients("Cardoons", "zibibbo", "zibibbo"), key=key)
    assert response.status_code == 201


@pytest.mark.django_db
def test_new_name_count_counts_each_kind_once(user):
    """Ingredients and substitutes together, units, tags and a cuisine, each name once."""
    document = {
        "format": "nutrisho",
        "version": 1,
        "recipes": [
            {
                "recipe_name": "Soup",
                "cuisine": "atlantis.north",
                "tags": ["odd", "Odd"],
                "ingredient_groups": [
                    {
                        "items": [
                            {"ingredient": "zibibbo", "substitute": "cardoon", "unit": "punnet"},
                            {"ingredient": "Cardoon", "unit": "small"},
                            {"ingredient": "salt", "unit": "g"},
                        ]
                    }
                ],
            }
        ],
    }
    Ingredient.objects.create(ingredient_name="salt")
    # zibibbo, cardoon, punnet, odd, atlantis.north: `small` never becomes a unit.
    assert new_name_count(parse_document(document), owner=user) == 5
