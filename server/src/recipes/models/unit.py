"""The canonical unit vocabulary and its input-only aliases (#67).

Same shape as ingredients and their aliases (plan 008): a recipe row points at
one `Unit`, and every spelling typed or imported (`Tbsp`, `tbs`, `tablespoons`)
resolves to it on input through `services/name_resolution.find_unit`.

A shared vocabulary like ingredients (#154): a global list curated by staff in
Django admin, plus each user's own units, made by `resolve_unit` when they type
or import one the server does not know. A private unit has no dimension until
staff make it global by clearing its owner. Aliases are global only.
"""

from typing import cast

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from recipes.utils.pluralise import pluralise

UNIT_NAME_MAX_LENGTH = 32


class Unit(models.Model):
    """One unit as recipes store it: the canonical singular, a plural, a dimension."""

    MASS = "mass"
    VOLUME = "volume"
    COUNT = "count"
    DIMENSION_CHOICES = [
        (MASS, "Mass"),
        (VOLUME, "Volume"),
        (COUNT, "Count"),
    ]

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=UNIT_NAME_MAX_LENGTH)
    plural_name = models.CharField(
        "plural display form; blank derives it from the rule",
        max_length=UNIT_NAME_MAX_LENGTH,
        blank=True,
        default="",
    )
    dimension = models.CharField(
        "blank only on a private unit",
        max_length=8,
        choices=DIMENSION_CHOICES,
        blank=True,
        default="",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="private to this user; blank means global (staff-curated)",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="private_units",
    )
    objects = models.Manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            # Unique ignoring case within the global list...
            models.UniqueConstraint(
                Lower("name"),
                condition=Q(owner__isnull=True),
                name="unit_name_ci_unique",
                violation_error_message="That unit already exists.",
            ),
            # ...and within each user's own. A private unit may share a name with
            # a global one, which wins at resolution (`find_unit`).
            models.UniqueConstraint(
                Lower("name"),
                F("owner"),
                name="unit_name_ci_unique_per_owner",
                violation_error_message="You already have that unit.",
            ),
        ]

    def __str__(self) -> str:
        """The canonical name."""
        return str(self.name)

    @property
    def plural(self) -> str:
        """Display form at a quantity other than 1: the override, else the rule.

        An override equal to `name` keeps an abbreviation invariant (`200 g`).
        """
        # cast: Django's CharField descriptor types as the field, not its value.
        return cast(str, self.plural_name) or pluralise(cast(str, self.name))

    def clean(self) -> None:
        """A global unit says what it measures; a private one may not know yet."""
        if self.owner_id is None and not self.dimension:
            raise ValidationError({"dimension": "A global unit needs a dimension."})


class UnitAlias(models.Model):
    """`alias_name` typed or imported means `unit` (`tablespoon` → `tbsp`).

    Input-only: no recipe references an alias, so storage and display always use
    the canonical unit. A name is a unit or an alias, never both.
    """

    id = models.AutoField(primary_key=True)
    alias_name = models.CharField(max_length=UNIT_NAME_MAX_LENGTH)
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="aliases")
    objects = models.Manager()

    class Meta:
        verbose_name_plural = "unit aliases"
        constraints = [
            models.UniqueConstraint(
                Lower("alias_name"),
                name="unit_alias_name_ci_unique",
                violation_error_message="That name is already a unit alias.",
            ),
        ]

    def __str__(self) -> str:
        """`alias → unit`."""
        return f"{self.alias_name} → {self.unit}"

    def clean(self) -> None:
        """Strip the name; it must not be a global unit's name, and the unit must be global."""
        self.alias_name = str(self.alias_name).strip()  # ty: ignore[invalid-assignment]  # CharField descriptor
        if Unit.objects.filter(owner__isnull=True, name__iexact=self.alias_name).exists():
            msg = f"“{self.alias_name}” is already a unit."
            raise ValidationError({"alias_name": msg})
        unit = Unit.objects.filter(pk=self.unit_id).first()
        if unit is not None and unit.owner_id is not None:
            msg = "Aliases are global, so they can only point at a global unit."
            raise ValidationError({"unit": msg})
