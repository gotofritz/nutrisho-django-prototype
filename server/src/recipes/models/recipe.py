from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse

from recipes.utils.plain_text import plain_text

from .cuisine import Cuisine

# Form-only cap on long prose (Recipe.short_description, Step.step_text). They
# are TextFields, so the database has no limit (#49).
PROSE_MAX_LENGTH = 4000

# Typed field -> the column holding its tag-free text (#32), kept in step by save().
_PLAIN_COLUMNS = {"recipe_name": "plain_name", "short_description": "plain_description"}


class RecipeQuerySet(models.QuerySet):
    """Recipes split by whether they are in the trash (#75)."""

    def live(self) -> RecipeQuerySet:
        """Recipes not in the trash: what every page shows."""
        return self.filter(deleted_at__isnull=True)

    def trashed(self) -> RecipeQuerySet:
        """Recipes in the trash, waiting to be restored or deleted for good."""
        return self.filter(deleted_at__isnull=False)


class Recipe(models.Model):
    """Recipe model.

    servings is the author's intended serving count. It is mandatory: every
    recipe carries one, and the column is NOT NULL with a default of 1.
    Ingredient quantities are stored as-is from the source data and are not
    normalized to per-serving amounts; a data migration is required before
    any per-serving arithmetic is meaningful.

    `recipe_name` and `short_description` are stored as typed, inline tags and
    all (#17). `plain_name` and `plain_description` hold the same text without
    tags, written by `save()`; search reads them, and a name is unique per owner
    by its plain text, so `Foo` and `<u>Foo</u>` clash (#32).

    Deleting a recipe moves it to the trash by setting `deleted_at` (#75); the
    row and its contents stay until it is restored or deleted for good. Pages
    read `Recipe.objects.live()`; the name rule covers live recipes only.
    """

    id = models.AutoField(primary_key=True)
    recipe_name = models.CharField("Recipe main name", max_length=200)
    short_description = models.TextField(
        "A short blurb about the recipe", max_length=PROSE_MAX_LENGTH, blank=True, default=""
    )
    # Annotated because, without Django stubs, ty types the attribute as the field
    owner: User = models.ForeignKey(User, on_delete=models.CASCADE, null=False)  # ty: ignore[invalid-assignment]
    # Free text: a book and page, or a web address, which the page links (#65).
    source_instance = models.CharField(
        "source",
        max_length=200,
        blank=True,
        help_text="A book and page, or a web address.",
    )
    cuisine = models.ForeignKey(Cuisine, on_delete=models.SET_NULL, null=True, blank=True)
    servings = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    created_date = models.DateTimeField("date created", auto_now_add=True)
    plain_name = models.CharField(
        "recipe_name without inline tags", max_length=200, editable=False, default=""
    )
    plain_description = models.TextField(
        "short_description without inline tags", editable=False, blank=True, default=""
    )
    # Set while the recipe is in the trash (#75); NULL for a live recipe.
    deleted_at = models.DateTimeField("moved to the trash", null=True, blank=True, editable=False)
    objects = models.Manager.from_queryset(RecipeQuerySet)()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(servings__gte=1),
                name="recipes_recipe_servings_gte1",
            ),
            models.UniqueConstraint(
                fields=["owner", "plain_name"],
                condition=models.Q(deleted_at__isnull=True),
                name="recipes_recipe_unique_plain_name_per_owner",
            ),
        ]

    def __str__(self) -> str:
        """Return a readable label."""
        return str(self.recipe_name)

    def save(self, *args: object, **kwargs: object) -> None:
        """Save, refreshing the plain-text columns of whichever fields are written."""
        for typed, plain in _PLAIN_COLUMNS.items():
            setattr(self, plain, plain_text(str(getattr(self, typed))))
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            fields = set(update_fields)  # ty: ignore[invalid-argument-type]  # an iterable of names
            fields |= {_PLAIN_COLUMNS[f] for f in fields if f in _PLAIN_COLUMNS}
            kwargs["update_fields"] = fields
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Return the URL of the recipe page."""
        return reverse("recipes:recipe", kwargs={"recipe_id": self.id})
