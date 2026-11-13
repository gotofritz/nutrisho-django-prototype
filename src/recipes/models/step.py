from django.db import models

from .recipe import PROSE_MAX_LENGTH, Recipe


class Step(models.Model):
    id = models.AutoField(primary_key=True)
    step_title = models.CharField(
        "An optional heading for a step",
        max_length=128,
        blank=True,
        default="",
    )
    step_text = models.TextField(
        "The description of a step",
        max_length=PROSE_MAX_LENGTH,
    )
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="steps")
    index_in_sequence = models.SmallIntegerField("What step is this, for a given recipe?")
    objects = models.Manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["index_in_sequence", "recipe"],
                name="unique Step in sequence",
            )
        ]
        ordering = ["index_in_sequence"]

    def __str__(self) -> str:
        """Return a readable label."""
        return f"{self.index_in_sequence}. {str(self.step_text)[:32]}"
