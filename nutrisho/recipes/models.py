from django.db import models


class Cuisine(models.Model):
    cuisine = models.CharField(
        "region.area.subarea just as placeholder", max_length=200
    )


class Recipe(models.Model):
    name = models.CharField("Recipe main name", max_length=200)
    short_description = models.CharField(
        "A short blurb about the recipe", max_length=200, null=True
    )
    source = models.CharField(
        "The URL or book where the recipe came from", max_length=200, null=True
    )
    cuisine = models.ForeignKey(Cuisine, on_delete=models.SET_NULL, null=True)
    created_date = models.DateTimeField("date created")


class Tag(models.Model):
    tag = models.CharField("Name of tag", max_length=64)
    recipe = models.ManyToManyField(Recipe)
