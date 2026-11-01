from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from .recipe import Recipe

TAG_MAX_LENGTH = 64


class Tag(models.Model):
    """A label on recipes: global (staff-curated) or private to one user (plan 011)."""

    id = models.AutoField(primary_key=True)
    tag = models.CharField("Name of tag", max_length=TAG_MAX_LENGTH)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="private to this user; blank means global (staff-curated)",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="private_tags",
    )
    recipe = models.ManyToManyField(
        Recipe,
        blank=True,
        related_name="tag",
    )
    objects = models.Manager()

    class Meta:
        constraints = [
            # Unique ignoring case within the global list and within each user's
            # private tags, mirroring Ingredient.
            models.UniqueConstraint(
                Lower("tag"), condition=Q(owner__isnull=True), name="tag_ci_unique"
            ),
            models.UniqueConstraint(Lower("tag"), F("owner"), name="tag_ci_unique_per_owner"),
        ]

    def __str__(self) -> str:
        """Return a readable label."""
        return str(self.tag)

    def natural_key(self):
        """Return the natural key used by fixtures."""
        return self.tag
