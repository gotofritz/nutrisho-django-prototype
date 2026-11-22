"""The lists the recipe clipper loads when its sidebar opens (#160, plan 012 M4).

The clipper checks a draft's names in the browser against these (D4), so each
ingredient and unit comes with every spelling the server accepts for it: its
plural, its aliases and their plurals. The clipper only looks names up here and
never inflects one itself, so the two sides cannot disagree about a plural.

A spelling two rows could claim is listed under the row `name_resolution` sends
it to: a name before a plural before an alias, the global row before the
user's own. A name the user has globally and privately is listed once, as the
global row. Each kind of data is read in one query, so the reply's cost does not
grow with the library. A later kind of data, such as nutrition, is a new section.
"""

from collections.abc import Iterable
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import F, Q

from recipes.models import Ingredient, IngredientAlias, Tag, Unit, UnitAlias
from recipes.services.name_resolution import cuisine_paths
from recipes.services.recipe_document import FIELD_LENGTHS
from recipes.utils.pluralise import pluralise


def vocabulary(*, owner: AbstractBaseUser) -> dict[str, Any]:
    """What `owner` can name in a recipe, in named sections."""
    return {
        "user": owner.get_username(),
        "ingredients": _ingredients(owner),
        "units": _units(owner),
        "cuisines": cuisine_paths(owner=owner),
        "tags": _tags(owner),
        "limits": dict(FIELD_LENGTHS),
    }


class _Spellings:
    """Entries by canonical name, each spelling held by the first entry to claim it."""

    def __init__(self) -> None:
        self._entries: dict[int, dict[str, Any]] = {}
        self._claimed: set[str] = set()

    def add(self, pk: int, name: str) -> bool:
        """A row's own name; False when an earlier row already has it."""
        if name.lower() in self._claimed:
            return False
        self._claimed.add(name.lower())
        self._entries[pk] = {"name": name, "spellings": []}
        return True

    def claim(self, pk: int, spellings: Iterable[str]) -> None:
        """Further spellings of row `pk`, each unless another row holds it already."""
        entry = self._entries.get(pk)
        if entry is None:
            return
        for spelling in spellings:
            if spelling.lower() not in self._claimed:
                self._claimed.add(spelling.lower())
                entry["spellings"].append(spelling)

    def entries(self) -> list[dict[str, Any]]:
        return sorted(self._entries.values(), key=lambda e: (e["name"].lower(), e["name"]))


def _ingredients(owner: AbstractBaseUser) -> list[dict[str, Any]]:
    """As `find_ingredient` resolves them: names, then plurals, then aliases."""
    rows = list(
        Ingredient.objects.filter(Q(owner__isnull=True) | Q(owner=owner)).order_by(
            F("owner").asc(nulls_first=True), "pk"
        )
    )
    spellings = _Spellings()
    kept = [row for row in rows if spellings.add(row.pk, str(row.ingredient_name))]
    for row in kept:
        spellings.claim(row.pk, [row.plural])
    # An alias's canonical is always global, so it is never another user's row.
    aliases = IngredientAlias.objects.filter(canonical__owner__isnull=True).order_by("pk")
    for canonical_id, alias in aliases.values_list("canonical_id", "alias_name"):
        spellings.claim(canonical_id, [alias, pluralise(alias)])
    return spellings.entries()


def _units(owner: AbstractBaseUser) -> list[dict[str, Any]]:
    """As `find_unit` resolves them: names, then plurals, then the global units' aliases."""
    rows = list(
        Unit.objects.filter(Q(owner__isnull=True) | Q(owner=owner)).order_by(
            F("owner").asc(nulls_first=True), "pk"
        )
    )
    spellings = _Spellings()
    kept = [row for row in rows if spellings.add(row.pk, str(row.name))]
    for row in kept:
        spellings.claim(row.pk, [row.plural])
    aliases = UnitAlias.objects.filter(unit__owner__isnull=True).order_by("pk")
    for unit_id, alias in aliases.values_list("unit_id", "alias_name"):
        spellings.claim(unit_id, [alias, pluralise(alias)])
    return spellings.entries()


def _tags(owner: AbstractBaseUser) -> list[str]:
    """Tag names, global and the user's own; a name in both is listed in the global spelling."""
    names: dict[str, str] = {}
    visible = Tag.objects.filter(Q(owner__isnull=True) | Q(owner=owner)).order_by(
        F("owner").asc(nulls_first=True), "pk"
    )
    for name in visible.values_list("tag", flat=True):
        names.setdefault(name.lower(), name)
    return sorted(names.values(), key=lambda n: (n.lower(), n))
