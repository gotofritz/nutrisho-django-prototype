"""A key that signs in a client that is not a browser, such as the recipe clipper (#78)."""

from django.conf import settings
from django.db import models


class ApiToken(models.Model):
    """One user's key for the JSON API, stored only as its SHA-256 digest.

    The key itself is shown once, when `services/api_tokens.create_token` makes
    it. A user may hold several, one per client; deleting a row revokes it.
    """

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens"
    )
    name = models.CharField("what it is for, e.g. clipper", max_length=64, blank=True, default="")
    key_digest = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True, editable=False)

    objects = models.Manager()

    class Meta:
        verbose_name = "API token"

    def __str__(self) -> str:
        """`name (username)`."""
        return f"{self.name or 'token'} ({self.user})"
