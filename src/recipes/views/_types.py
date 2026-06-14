"""Shared view type aliases."""

from django.contrib.auth.models import AbstractBaseUser
from django.http import HttpRequest


class AuthedRequest(HttpRequest):
    """HttpRequest subclass that documents the `user` attribute set by AuthenticationMiddleware."""

    user: AbstractBaseUser  # type: ignore[assignment]  # narrowed from AbstractBaseUser | AnonymousUser
