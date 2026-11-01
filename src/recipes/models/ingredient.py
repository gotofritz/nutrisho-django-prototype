from typing import cast

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from recipes.utils.pluralise import pluralise

# Imported data has a 72-character name (#49). plural_name shares the limit:
# merging a plural pair writes one ingredient name into the other's plural_name.
INGREDIENT_NAME_MAX_LENGTH = 128


class Ingredient(models.Model):
    id = models.AutoField(primary_key=True)
    CONSTRAINT_CHOICES = [
        ("PSC", "Pescatarian"),
        ("VGT", "Vegetarian"),
        ("VGN", "Vegan"),
    ]
    GROUP_CHOICES = [
        ("VEG", "Vegetable"),
        ("MEA", "Meat"),
        ("SEA", "Seafood"),
        ("FSH", "Fish"),
        ("GRA", "Grain"),
        ("GRN", "Green"),
        ("SPI", "Spice"),
        ("CHE", "Cheese"),
        ("MLK", "Milk product"),
        ("FAT", "Fat"),
        ("CND", "Condiment"),
        ("PUL", "Pulse"),
        ("NUT", "Nut"),
        ("SEE", "Seed"),
        ("FRU", "Fruit"),
        ("EGG", "Egg"),
        ("CHM", "Chemical"),
        ("MSC", "Misc"),
    ]
    ingredient_name = models.CharField(max_length=INGREDIENT_NAME_MAX_LENGTH)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="private to this user; blank means global (staff-curated)",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="private_ingredients",
    )
    plural_name = models.CharField(
        "plural display form; blank derives it from the rule",
        max_length=INGREDIENT_NAME_MAX_LENGTH,
        blank=True,
        default="",
    )
    dietary_constraint = models.CharField(
        "vegetarian etc", choices=CONSTRAINT_CHOICES, blank=True, max_length=32
    )
    family = models.CharField(
        "Broad ingredient category (vegetable, spice, ...)",
        max_length=32,
        choices=GROUP_CHOICES,
        blank=True,
    )
    objects = models.Manager()

    class Meta:
        constraints = [
            # British spelling is canonical, so Onion and onion are the same
            # ingredient: unique ignoring case within the global list...
            models.UniqueConstraint(
                Lower("ingredient_name"),
                condition=Q(owner__isnull=True),
                name="ingredient_name_ci_unique",
            ),
            # ...and within each user's private list. A private row may share a
            # name with another user's row, or with a global one (which wins
            # at resolution, see recipes.services.name_resolution).
            models.UniqueConstraint(
                Lower("ingredient_name"),
                F("owner"),
                name="ingredient_name_ci_unique_per_owner",
            ),
        ]

    def __str__(self) -> str:
        """Return a readable label."""
        return str(self.ingredient_name)

    @property
    def plural(self) -> str:
        """Display form at a quantity other than 1: the override, else the rule.

        Presentation only — nothing persists or exports the plural. An override
        equal to `ingredient_name` is how an invariant noun (`broccoli`, `fish`)
        opts out of inflection.
        """
        # cast: Django's CharField descriptor types as the field, not its value.
        return cast(str, self.plural_name) or pluralise(cast(str, self.ingredient_name))

    def natural_key(self):
        """Return the natural key used by fixtures."""
        return self.ingredient_name
