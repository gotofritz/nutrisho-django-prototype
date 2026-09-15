from typing import cast

from django.db import models
from django.db.models.functions import Lower

from recipes.utils.pluralise import pluralise


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
    ingredient_name = models.CharField(max_length=64, unique=True)
    plural_name = models.CharField(
        "plural display form; blank derives it from the rule",
        max_length=64,
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
        return self.ingredient_name

    class Meta:
        constraints = [
            # British spelling is canonical, so Onion and onion are the same
            # ingredient. Clear existing clashes with the find_ingredient_duplicates
            # command and the clean-up tool before applying this.
            models.UniqueConstraint(
                Lower("ingredient_name"),
                name="ingredient_name_ci_unique",
            )
        ]
