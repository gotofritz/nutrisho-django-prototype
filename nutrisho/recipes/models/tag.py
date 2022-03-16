from django.db import models

from .recipe import Recipe


class Tag(models.Model):
    tag = models.CharField("Name of tag", max_length=64, unique=True)
    recipe = models.ManyToManyField(Recipe, blank=True)

    def natural_key(self):
        return self.tag
