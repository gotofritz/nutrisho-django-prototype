from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse

from .cuisine import Cuisine
from .source import Source


class Recipe(models.Model):
    id = models.AutoField(primary_key=True)
    recipe_name = models.CharField("Recipe main name", max_length=200, unique=True)
    short_description = models.CharField(
        "A short blurb about the recipe", max_length=512, blank=True, null=True
    )
    owner = models.ForeignKey(User, on_delete=models.SET_DEFAULT, default=2, null=False)
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    source_instance = models.CharField(
        "For example, the page if source is a book, or URL if source is a website",
        max_length=200,
        blank=True,
    )
    cuisine = models.ForeignKey(Cuisine, on_delete=models.SET_NULL, null=True, blank=True)
    created_date = models.DateTimeField("date created", auto_now_add=True)
    objects = models.Manager()

    def natural_key(self):
        return self.recipe_name

    def get_absolute_url(self):
        return reverse("recipes:recipe", kwargs={"recipe_id": self.id})
