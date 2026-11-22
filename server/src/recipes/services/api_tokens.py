"""Make API tokens and sign a request in with one (#78).

A key is `nsh_` and 43 random URL-safe characters, sent as
`Authorization: Bearer <key>`. Only its SHA-256 digest is stored: the key has
256 bits of randomness, so a plain hash is as strong as a slow one, and a
lookup by digest gives nothing away by its timing.

A key expires (#149) on its own `expires_at`, if it has one, or once unused for
`settings.API_TOKEN_IDLE_DAYS`, counted from its last use or, if never used,
from when it was made. An expired key raises `TokenExpiredError`, so the
caller can say to make a new one; any other wrong key is just no user.

Users make their own on the API keys page (#150), at most
`MAX_TOKENS_PER_USER` each; `create_api_token` makes one for any user.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import cast

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from recipes.models import ApiToken

TOKEN_PREFIX = "nsh_"
MAX_TOKENS_PER_USER = 10


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class TokenExpiredError(Exception):
    """The key was a real one, but has expired: past its date, or unused too long."""


class TokenLimitError(Exception):
    """The user already holds `MAX_TOKENS_PER_USER` keys."""


def create_token(
    *, user: AbstractBaseUser, name: str = "", days: int | None = None
) -> tuple[ApiToken, str]:
    """A new token for `user`, expiring after `days` if given, and its key, which nothing can show again."""
    key = TOKEN_PREFIX + secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(days=days) if days else None
    with transaction.atomic():
        token = ApiToken.objects.create(
            user=user, name=name, key_digest=_digest(key), expires_at=expires_at
        )
    return token, key


def make_own_token(
    *, user: AbstractBaseUser, name: str, days: int | None = None
) -> tuple[ApiToken, str]:
    """`create_token`, refused with `TokenLimitError` once `user` holds the most keys allowed."""
    with transaction.atomic():
        if ApiToken.objects.filter(user=user).count() >= MAX_TOKENS_PER_USER:
            raise TokenLimitError
        return create_token(user=user, name=name, days=days)


def user_tokens(*, user: AbstractBaseUser) -> list[ApiToken]:
    """`user`'s own tokens, newest first."""
    return list(ApiToken.objects.filter(user=user).order_by("-created_at", "-pk"))


def idle_since(token: ApiToken) -> datetime:
    """When the token was last used, or made if it never was."""
    return cast("datetime", token.last_used_at or token.created_at)


def expires_on(token: ApiToken) -> datetime | None:
    """When `token` expires if left unused: its own date or the end of its idle days, whichever is sooner."""
    idle_days = settings.API_TOKEN_IDLE_DAYS
    limits = [
        cast("datetime | None", token.expires_at),
        idle_since(token) + timedelta(days=idle_days) if idle_days else None,
    ]
    return min((when for when in limits if when is not None), default=None)


def is_expired(token: ApiToken, *, now: datetime | None = None) -> bool:
    """Whether `token` is past its own date or has been unused too long."""
    when = expires_on(token)
    return when is not None and when <= (now or timezone.now())


def bearer_key(header: str) -> str:
    """The key in an `Authorization: Bearer <key>` header, or "" for anything else."""
    scheme, _, key = header.strip().partition(" ")
    return key.strip() if scheme.lower() == "bearer" else ""


def user_for_key(key: str) -> AbstractBaseUser | None:
    """The active user `key` belongs to, noting the use; None for any other key.

    Raises `TokenExpiredError` for a key that has expired, without noting a use.
    """
    if not key:
        return None
    with transaction.atomic():
        token = ApiToken.objects.select_related("user").filter(key_digest=_digest(key)).first()
        if token is None or not token.user.is_active:
            return None
        now = timezone.now()
        if is_expired(token, now=now):
            raise TokenExpiredError
        ApiToken.objects.filter(pk=token.pk).update(last_used_at=now)
    return token.user
