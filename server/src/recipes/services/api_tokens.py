"""Make API tokens and sign a request in with one (#78).

A key is `nsh_` and 43 random URL-safe characters, sent as
`Authorization: Bearer <key>`. Only its SHA-256 digest is stored: the key has
256 bits of randomness, so a plain hash is as strong as a slow one, and a
lookup by digest gives nothing away by its timing.
"""

import hashlib
import secrets

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from recipes.models import ApiToken

TOKEN_PREFIX = "nsh_"


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_token(*, user: AbstractBaseUser, name: str = "") -> tuple[ApiToken, str]:
    """A new token for `user`, and its key, which nothing can show again."""
    key = TOKEN_PREFIX + secrets.token_urlsafe(32)
    with transaction.atomic():
        token = ApiToken.objects.create(user=user, name=name, key_digest=_digest(key))
    return token, key


def bearer_key(header: str) -> str:
    """The key in an `Authorization: Bearer <key>` header, or "" for anything else."""
    scheme, _, key = header.strip().partition(" ")
    return key.strip() if scheme.lower() == "bearer" else ""


def user_for_key(key: str) -> AbstractBaseUser | None:
    """The active user `key` belongs to, noting the use; None for any other key."""
    if not key:
        return None
    with transaction.atomic():
        token = ApiToken.objects.select_related("user").filter(key_digest=_digest(key)).first()
        if token is None or not token.user.is_active:
            return None
        ApiToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
    return token.user
