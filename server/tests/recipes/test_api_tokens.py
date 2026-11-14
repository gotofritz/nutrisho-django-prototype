"""Tests for the API tokens that sign in a client that is not a browser (#78)."""

import hashlib
from io import StringIO

import pytest
from django.contrib import admin
from django.core.management import CommandError, call_command
from django.test import RequestFactory

from recipes.models import ApiToken
from recipes.services.api_tokens import TOKEN_PREFIX, bearer_key, create_token, user_for_key


@pytest.mark.django_db
def test_create_token_stores_only_a_digest(user):
    """The key is shown once; the database holds its SHA-256, never the key."""
    token, key = create_token(user=user, name="clipper")
    assert key.startswith(TOKEN_PREFIX)
    assert len(key) > 40
    assert token.key_digest == hashlib.sha256(key.encode()).hexdigest()
    assert key not in str(ApiToken.objects.values_list().get(pk=token.pk))
    assert str(token) == "clipper (gotofritz)"


@pytest.mark.django_db
def test_user_for_key(user):
    """A key signs in its user and notes when it was last used."""
    token, key = create_token(user=user)
    assert token.last_used_at is None
    assert user_for_key(key) == user
    token.refresh_from_db()
    assert token.last_used_at is not None


@pytest.mark.django_db
@pytest.mark.parametrize("key", ["", "nsh_wrong", "x" * 10_000])
def test_user_for_key_refuses_an_unknown_key(user, key: str):
    """No user for a key nobody holds."""
    create_token(user=user)
    assert user_for_key(key) is None


@pytest.mark.django_db
def test_user_for_key_refuses_an_inactive_user(user):
    """A deactivated account's keys stop working with it."""
    _, key = create_token(user=user)
    user.is_active = False
    user.save(update_fields=["is_active"])
    assert user_for_key(key) is None


@pytest.mark.django_db
def test_deleting_a_token_revokes_it(user):
    """There is no other state: a deleted token is gone."""
    token, key = create_token(user=user)
    token.delete()
    assert user_for_key(key) is None


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer nsh_abc", "nsh_abc"),
        ("bearer   nsh_abc  ", "nsh_abc"),
        ("Basic dXNlcjpwYXNz", ""),
        ("Bearer", ""),
        ("", ""),
    ],
)
def test_bearer_key(header: str, expected: str):
    """The key from an `Authorization: Bearer` header, or "" for any other."""
    assert bearer_key(header) == expected


@pytest.mark.django_db
def test_create_api_token_command(user):
    """The command prints a new key for a named user."""
    out = StringIO()
    call_command("create_api_token", "gotofritz", "--name", "clipper", stdout=out)
    key = next(line for line in out.getvalue().splitlines() if line.startswith(TOKEN_PREFIX))
    assert user_for_key(key) == user
    assert ApiToken.objects.get(user=user).name == "clipper"


@pytest.mark.django_db
def test_create_api_token_command_with_an_unknown_user():
    """No such user, no token."""
    with pytest.raises(CommandError, match="No user named “nobody”"):
        call_command("create_api_token", "nobody")
    assert not ApiToken.objects.exists()


@pytest.mark.django_db
def test_admin_lists_and_deletes_but_never_adds(user, admin_user):
    """Admin can revoke a token, but a key made there could never be shown."""
    model_admin = admin.site._registry[ApiToken]
    request = RequestFactory().get("/admin/")
    request.user = admin_user
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert model_admin.has_delete_permission(request)
