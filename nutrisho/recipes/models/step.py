from django.db import models
from typing import cast

from .recipe import Recipe


class Step(models.Model):
    id = models.AutoField(primary_key=True)
    step_text = models.CharField(
        "The description of a step",
        max_length=512,
    )
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="step")
    index_in_sequence = models.SmallIntegerField(
        "What step is this, for a given recipe?"
    )
    duration = models.DurationField("How long the step should take", null=True)
    extra_info = models.CharField(
        "any extra info",
        max_length=512,
        blank=True,
    )
    objects = models.Manager()

    def natural_key(self):
        return (self.index_in_sequence, cast(str, self.step_text)[:32])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["index_in_sequence", "recipe"],
                name="unique Step in sequence",
            )
        ]
        ordering = ["index_in_sequence"]
