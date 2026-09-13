"""Shared view type aliases."""

from django.contrib.auth.models import AbstractBaseUser
from django.http import HttpRequest
from django_htmx.middleware import HtmxDetails


class AuthedRequest(HttpRequest):
    """HttpRequest subclass documenting the attributes middleware attaches to the request."""

    user: AbstractBaseUser  # type: ignore[assignment]  # narrowed from AbstractBaseUser | AnonymousUser
    htmx: HtmxDetails  # set by django-htmx's HtmxMiddleware
