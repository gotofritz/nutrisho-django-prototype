"""API keys on the Config page (#150, plan 012 M14).

A user makes a key, which the page shows once; sees their keys by name, when
they were made and last used, and when they expire; and revokes one. Only their
own: another user's key is a 404 and is left alone.
"""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from recipes.models import ApiToken
from recipes.services.api_tokens import (
    MAX_TOKENS_PER_USER,
    TokenLimitError,
    create_token,
    expires_on,
    idle_since,
    make_own_token,
    user_for_key,
)

KEYS = "/recipes/keys/"


def _revoke(token: ApiToken) -> str:
    return f"/recipes/keys/{token.pk}/revoke/"


# --- The service -------------------------------------------------------------------


@pytest.mark.django_db
def test_a_user_may_hold_only_so_many_keys(user):
    """Past the cap, a new key is refused and none is made."""
    for n in range(MAX_TOKENS_PER_USER):
        make_own_token(user=user, name=f"key {n}")
    with pytest.raises(TokenLimitError):
        make_own_token(user=user, name="one too many")
    assert ApiToken.objects.filter(user=user).count() == MAX_TOKENS_PER_USER


@pytest.mark.django_db
def test_expires_on_is_the_sooner_of_the_two_limits(user, settings):
    """Its own date, or the day it would go idle, whichever comes first; None if neither."""
    settings.API_TOKEN_IDLE_DAYS = 90
    lasting, _ = create_token(user=user)
    dated, _ = create_token(user=user, days=30)
    assert expires_on(dated) == dated.expires_at
    assert expires_on(lasting) == idle_since(lasting) + timedelta(days=90)
    settings.API_TOKEN_IDLE_DAYS = 0
    assert expires_on(lasting) is None


# --- The Config page ------------------------------------------------------------------


@pytest.mark.django_db
def test_config_links_to_the_keys_page(auth_client):
    """Every user, not only staff, finds it on the Config page."""
    assert KEYS in auth_client.get("/recipes/config/").content.decode()


# --- Listing ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_page_lists_only_the_users_own_keys(auth_client, user, other_user):
    """Name, made, last used and expiry; another user's key is not there."""
    mine, _ = create_token(user=user, name="Firefox clipper")
    create_token(user=other_user, name="Someone's laptop")
    ApiToken.objects.filter(pk=mine.pk).update(last_used_at=timezone.now())
    html = auth_client.get(KEYS).content.decode()
    assert "Firefox clipper" in html
    assert "Someone&#x27;s laptop" not in html
    assert "Someone's laptop" not in html
    assert "Last used" in html
    assert "Expires" in html


@pytest.mark.django_db
def test_a_key_never_used_says_so(auth_client, user):
    """Rather than a blank last use."""
    create_token(user=user, name="clipper")
    assert "Never used" in auth_client.get(KEYS).content.decode()


@pytest.mark.django_db
def test_an_expired_key_says_so(auth_client, user):
    """So the user knows to revoke it and make a new one."""
    token, _ = create_token(user=user, name="clipper", days=1)
    ApiToken.objects.filter(pk=token.pk).update(expires_at=timezone.now() - timedelta(days=1))
    assert "Expired" in auth_client.get(KEYS).content.decode()


@pytest.mark.django_db
def test_no_keys_says_so(auth_client):
    """An empty list says what to do instead."""
    assert "You have no API keys yet." in auth_client.get(KEYS).content.decode()


@pytest.mark.django_db
def test_the_page_never_shows_a_stored_key(auth_client, user):
    """Only the digest is stored, and it is never sent either."""
    token, key = create_token(user=user, name="clipper")
    html = auth_client.get(KEYS).content.decode()
    assert key not in html
    assert token.key_digest not in html


# --- Making one -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_making_a_key_shows_it_once(auth_client, user):
    """The new key is on the page that answers the post, with a copy button, and works."""
    response = auth_client.post(KEYS, {"name": "Firefox clipper", "days": ""})
    assert response.status_code == 200
    html = response.content.decode()
    token = ApiToken.objects.get(user=user)
    assert token.name == "Firefox clipper"
    assert token.expires_at is None
    key = response.context["new_key"]
    assert key.startswith("nsh_")
    assert key in html
    assert "data-copy=" in html
    assert "cannot be shown again" in html
    assert "no-store" in response["Cache-Control"]
    assert user_for_key(key) == user
    assert key not in auth_client.get(KEYS).content.decode()


@pytest.mark.django_db
def test_a_key_can_be_given_a_date(auth_client, user):
    """`days` sets `expires_at`."""
    auth_client.post(KEYS, {"name": "clipper", "days": "30"})
    expires_at = ApiToken.objects.get(user=user).expires_at
    assert expires_at is not None
    assert timedelta(days=29) < expires_at - timezone.now() <= timedelta(days=30)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("data", "field"),
    [({"name": "", "days": ""}, "name"), ({"name": "x" * 65, "days": ""}, "name")],
)
def test_a_key_needs_a_short_name(auth_client, user, data, field):
    """A name says which client the key is for, so a lost one is easy to revoke."""
    response = auth_client.post(KEYS, data)
    assert response.status_code == 200
    assert response.context["form"].errors[field]
    assert "new_key" not in response.context
    assert not ApiToken.objects.exists()


@pytest.mark.django_db
def test_a_date_not_offered_is_refused(auth_client):
    """Only the offered dates are taken."""
    response = auth_client.post(KEYS, {"name": "clipper", "days": "7"})
    assert response.context["form"].errors["days"]
    assert not ApiToken.objects.exists()


@pytest.mark.django_db
def test_one_key_too_many_is_refused_on_the_page(auth_client, user):
    """The form says to revoke one first, and no key is made."""
    for n in range(MAX_TOKENS_PER_USER):
        create_token(user=user, name=f"key {n}")
    response = auth_client.post(KEYS, {"name": "one too many", "days": ""})
    assert response.status_code == 200
    assert "revoke one first" in response.content.decode()
    assert "new_key" not in response.context
    assert ApiToken.objects.filter(user=user).count() == MAX_TOKENS_PER_USER


# --- Revoking one ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_revoking_a_key_deletes_it(auth_client, user):
    """Behind a confirmation; the key stops working and the page says so."""
    token, key = create_token(user=user, name="clipper")
    html = auth_client.get(KEYS).content.decode()
    assert _revoke(token) in html
    assert "hx-confirm=" in html
    response = auth_client.post(_revoke(token), follow=True)
    assert response.redirect_chain[-1][0] == KEYS
    assert "Revoked “clipper”." in response.content.decode()
    assert not ApiToken.objects.exists()
    assert user_for_key(key) is None


@pytest.mark.django_db
def test_another_users_key_is_a_404(user, other_user):
    """Even for staff, and it is left alone."""
    token, _ = create_token(user=user, name="clipper")
    other_user.is_staff = True
    other_user.save()
    client = Client()
    client.force_login(other_user)
    assert client.post(_revoke(token)).status_code == 404
    assert ApiToken.objects.filter(pk=token.pk).exists()


@pytest.mark.django_db
def test_revoke_takes_only_a_post(auth_client, user):
    """A GET changes nothing."""
    token, _ = create_token(user=user, name="clipper")
    assert auth_client.get(_revoke(token)).status_code == 405
    assert ApiToken.objects.exists()
