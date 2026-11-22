from typing import cast

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

# area.region.subregion, e.g. med.italy.sicily (plan 011).
MAX_CUISINE_DEPTH = 3
PATH_SEPARATOR = "."
CUISINE_MAX_LENGTH = 200


class Cuisine(models.Model):
    """One node of the cuisine tree: an area, a region or a subregion.

    A recipe may point at any depth: `middle east` for a dish many countries
    claim, `med.italy` with no region given, or `med.italy.sicily`. The global
    tree (no owner) is curated by staff; a cuisine a user types that they
    cannot see becomes a node private to them (#171), inside a global node or
    one of their own, never another user's.
    """

    id = models.AutoField(primary_key=True)
    cuisine = models.CharField("name of this node, e.g. sicily", max_length=CUISINE_MAX_LENGTH)
    parent = models.ForeignKey(
        "self",
        verbose_name="the area or region this belongs to; blank for an area",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="private to this user; blank means global (staff-curated)",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="private_cuisines",
    )
    objects = models.Manager()

    class Meta:
        constraints = [
            # Names are unique ignoring case among siblings: `north` may appear
            # under thailand and vietnam, but not twice under either. Areas
            # (no parent) need their own constraint, since NULLs never clash.
            # The global tree and each user's own nodes are checked apart, as
            # for tags: two users may each have a `marche` under med.italy.
            models.UniqueConstraint(
                Lower("cuisine"),
                condition=Q(parent__isnull=True, owner__isnull=True),
                name="cuisine_ci_unique",
            ),
            models.UniqueConstraint(
                Lower("cuisine"),
                F("parent"),
                condition=Q(owner__isnull=True),
                name="cuisine_ci_unique_per_parent",
            ),
            models.UniqueConstraint(
                Lower("cuisine"),
                F("owner"),
                condition=Q(parent__isnull=True, owner__isnull=False),
                name="cuisine_ci_unique_private",
            ),
            models.UniqueConstraint(
                Lower("cuisine"),
                F("parent"),
                F("owner"),
                condition=Q(owner__isnull=False),
                name="cuisine_ci_unique_private_per_parent",
            ),
        ]

    def __str__(self) -> str:
        """Return the dotted path, e.g. `med.italy.sicily`."""
        return self.path

    @property
    def parent_node(self) -> Cuisine | None:
        """`parent`, typed: ty reads the FK descriptor as the field, not the row."""
        return cast("Cuisine | None", self.parent)

    @property
    def ancestors(self) -> list[Cuisine]:
        """The chain from the area down to the parent, excluding this node."""
        chain: list[Cuisine] = []
        node = self.parent_node
        while node is not None and node not in chain and len(chain) <= MAX_CUISINE_DEPTH:
            chain.insert(0, node)
            node = node.parent_node
        return chain

    @property
    def path(self) -> str:
        """`area.region.subregion`, as far down as this node goes."""
        return PATH_SEPARATOR.join([*(str(a.cuisine) for a in self.ancestors), str(self.cuisine)])

    def clean(self) -> None:
        """Reject dots in names, loops, nodes deeper than three levels, and hidden parents."""
        if PATH_SEPARATOR in str(self.cuisine):
            msg = f"A cuisine name cannot contain '{PATH_SEPARATOR}'."
            raise ValidationError({"cuisine": msg})
        parent = self.parent_node
        if parent is None:
            return
        if parent.owner_id is not None and parent.owner_id != self.owner_id:
            msg = (
                "A global cuisine cannot sit inside a private one."
                if self.owner_id is None
                else "A cuisine cannot sit inside another user's."
            )
            raise ValidationError({"parent": msg})
        if self.pk is not None and any(a.pk == self.pk for a in [*parent.ancestors, parent]):
            raise ValidationError({"parent": "A cuisine cannot sit inside itself."})
        depth = len(parent.ancestors) + 2
        if self.pk is not None:
            # Moving a node moves its children too.
            if Cuisine.objects.filter(parent__parent=self).exists():
                depth += 2
            elif Cuisine.objects.filter(parent=self).exists():
                depth += 1
        if depth > MAX_CUISINE_DEPTH:
            msg = f"Cuisines go at most {MAX_CUISINE_DEPTH} levels deep (area.region.subregion)."
            raise ValidationError({"parent": msg})
