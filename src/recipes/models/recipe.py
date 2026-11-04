from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse

from .cuisine import Cuisine
from .source import Source

# Form-only cap on long prose (Recipe.short_description, Step.step_text and
# .extra_info). They are TextFields, so the database has no limit (#49).
PROSE_MAX_LENGTH = 4000


class Recipe(models.Model):
    """Recipe model.

    servings is the author's intended serving count. It is mandatory: every
    recipe carries one, and the column is NOT NULL with a default of 1.
    Ingredient quantities are stored as-is from the source data and are not
    normalized to per-serving amounts; a data migration is required before
    any per-serving arithmetic is meaningful.
    """

    id = models.AutoField(primary_key=True)
    recipe_name = models.CharField("Recipe main name", max_length=200)
    short_description = models.TextField(
        "A short blurb about the recipe", max_length=PROSE_MAX_LENGTH, blank=True, default=""
    )
    # Annotated because, without Django stubs, ty types the attribute as the field
    owner: User = models.ForeignKey(User, on_delete=models.CASCADE, null=False)  # ty: ignore[invalid-assignment]
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    source_instance = models.CharField(
        "For example, the page if source is a book, or URL if source is a website",
        max_length=200,
        blank=True,
    )
    cuisine = models.ForeignKey(Cuisine, on_delete=models.SET_NULL, null=True, blank=True)
    servings = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    created_date = models.DateTimeField("date created", auto_now_add=True)
    objects = models.Manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(servings__gte=1),
                name="recipes_recipe_servings_gte1",
            ),
            models.UniqueConstraint(
                fields=["owner", "recipe_name"],
                name="recipes_recipe_unique_name_per_owner",
            ),
        ]

    def __str__(self) -> str:
        """Return a readable label."""
        return str(self.recipe_name)

    def get_absolute_url(self):
        """Return the URL of the recipe page."""
        return reverse("recipes:recipe", kwargs={"recipe_id": self.id})
