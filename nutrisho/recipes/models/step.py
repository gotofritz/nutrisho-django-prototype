from django.db import models

from .recipe import Recipe


class Step(models.Model):
    step = models.CharField(
        "The description of a step",
        max_length=512,
    )
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="step")
    index_in_sequence = models.SmallIntegerField(
        "What step is this, for a given recipe?"
    )
    duration = models.DurationField("How long the step should take", null=True)
    extra_info = models.CharField(
        "extra information, for example how to peel tomatoes", max_length=512, null=True
    )

    def natural_key(self):
        return (self.index_in_sequence, self.step[:32])

    # def __str__:
    #     related_name='recipe'

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["index_in_sequence", "recipe"],
                name="unique Step in sequence",
            )
        ]
        ordering = ["index_in_sequence"]
