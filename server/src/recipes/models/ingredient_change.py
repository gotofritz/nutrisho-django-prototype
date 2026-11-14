"""A record of one clean-up tool change to the shared ingredients, for Undo (#75)."""

from django.conf import settings
from django.db import models


class IngredientChange(models.Model):
    """What one merge, delete, plural merge, promote or alias did, step by step.

    `events` is a list of steps in the order they were written; Undo replays
    them backwards (`services/ingredient_journal.py`). Only the newest change
    that has not been undone can be undone, so the steps always meet the data
    as they left it, apart from recipe edits made since.
    """

    id = models.AutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    summary = models.CharField(max_length=500, blank=True, default="")
    events = models.JSONField(default=list)
    undone_at = models.DateTimeField(null=True, blank=True)
    objects = models.Manager()

    def __str__(self) -> str:
        """The summary."""
        return str(self.summary)
