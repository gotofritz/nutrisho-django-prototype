from django.db import models

from .recipe import Recipe


class Tag(models.Model):
    id = models.AutoField(primary_key=True)
    tag = models.CharField("Name of tag", max_length=64, unique=True)
    recipe = models.ManyToManyField(
        Recipe,
        blank=True,
        related_name="tag",
    )
    objects = models.Manager()

    def natural_key(self):
        return self.tag
