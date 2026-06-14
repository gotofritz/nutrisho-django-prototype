from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse

from recipes.utils.filename import sanitize_stored_filename

from .cuisine import Cuisine
from .source import Source


class RecipeManager(models.Manager):
    def get_by_natural_key(self, username: str, recipe_name: str) -> "Recipe":
        return self.get(owner__username=username, recipe_name=recipe_name)


class Recipe(models.Model):
    """
    Recipe model.

    servings is the author's intended serving count (default 1).
    Ingredient quantities are stored as-is from the source data and are not
    normalized to per-serving amounts; a data migration is required before
    any per-serving arithmetic is meaningful.
    """

    id = models.AutoField(primary_key=True)
    recipe_name = models.CharField("Recipe main name", max_length=200)
    short_description = models.CharField(
        "A short blurb about the recipe", max_length=512, blank=True, default=""
    )
    owner = models.ForeignKey(User, on_delete=models.CASCADE, null=False)
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    source_instance = models.CharField(
        "For example, the page if source is a book, or URL if source is a website",
        max_length=200,
        blank=True,
    )
    cuisine = models.ForeignKey(Cuisine, on_delete=models.SET_NULL, null=True, blank=True)
    servings = models.PositiveSmallIntegerField(
        null=True, blank=True, default=None, validators=[MinValueValidator(1)]
    )
    yaml_filename = models.CharField("source YAML filename", max_length=260, blank=True, default="")
    created_date = models.DateTimeField("date created", auto_now_add=True)
    objects = RecipeManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(servings__isnull=True) | models.Q(servings__gte=1),
                name="recipes_recipe_servings_gte1_or_null",
            ),
            models.UniqueConstraint(
                fields=["owner", "recipe_name"],
                name="recipes_recipe_unique_name_per_owner",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.yaml_filename:
            self.yaml_filename = sanitize_stored_filename(str(self.yaml_filename))
        super().save(*args, **kwargs)

    def natural_key(self) -> tuple[str, str]:
        return (str(self.owner.username), str(self.recipe_name))  # type: ignore[union-attr]

    natural_key.dependencies = ["auth.user"]  # type: ignore[attr-defined]

    def get_absolute_url(self):
        return reverse("recipes:recipe", kwargs={"recipe_id": self.id})
