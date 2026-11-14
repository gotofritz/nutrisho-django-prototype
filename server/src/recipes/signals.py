"""Signal receivers wired up in RecipesConfig.ready()."""

import logging

from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver
from django.http import HttpRequest

auth_logger = logging.getLogger("recipes.auth")


@receiver(user_login_failed)
def log_failed_login(
    sender: object,  # noqa: ARG001 - signal signature
    credentials: dict[str, str],
    request: HttpRequest | None = None,
    **_kwargs: object,
) -> None:
    """Warn about a failed login. Django masks the password in credentials; only the username is logged."""
    username = credentials.get("username", "")
    ip = request.META.get("REMOTE_ADDR", "") if request is not None else ""
    auth_logger.warning("Failed login for username=%r from ip=%s", username, ip or "unknown")
