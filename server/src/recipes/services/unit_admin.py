"""Query and mutation services for the staff unit tool (#154).

Pure ORM helpers with no HTTP concerns, like `cuisine_admin` and
`ingredient_admin`, so the HTMX views in `recipes/views/unit_admin.py` stay
thin. Units are global (staff-curated) or private to one user; a private unit
is invisible to everyone else, so it may only replace units in its owner's own
recipes. `IngredientInRecipe.unit` is PROTECT: every row is repointed, or keeps
the unit's name as `legacy_unit` text, before a unit is deleted.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.db.models import Count, QuerySet
from django.db.models.functions import Lower

from recipes.models import IngredientInRecipe, Recipe, Unit, UnitAlias


class UnitScopeError(Exception):
    """Raised when a private unit would land in another user's recipe; nothing is written."""


@dataclass(frozen=True)
class UnitRow:
    """One line of the tool's list: the unit, whose it is, its spellings and its use."""

    unit: Unit
    owner_name: str
    aliases: list[str]
    row_count: int


def unit_rows(
    query: str = "",
    *,
    private_only: bool = False,
    unused_only: bool = False,
    by_added: bool = False,
) -> list[UnitRow]:
    """Every unit whose name or an alias contains `query` (ignoring case), A to Z.

    `private_only` keeps the units users made, which wait for curation;
    `unused_only` the ones no row of any user's recipe points at. `by_added`
    sorts oldest first instead (by primary key, as there is no timestamp).
    Three queries whatever the vocabulary's size.
    """
    counts = dict(
        IngredientInRecipe.objects.filter(unit__isnull=False)
        .values_list("unit")
        .annotate(n=Count("pk"))
        .values_list("unit", "n")
    )
    aliases: dict[int, list[str]] = defaultdict(list)
    for unit_id, name in UnitAlias.objects.order_by(Lower("alias_name")).values_list(
        "unit_id", "alias_name"
    ):
        aliases[unit_id].append(name)
    units = Unit.objects.select_related("owner")
    if private_only:
        units = units.filter(owner__isnull=False)
    needle = query.strip().lower()
    rows = [
        UnitRow(
            unit=unit,
            owner_name=unit.owner.get_username() if unit.owner is not None else "",
            aliases=aliases[unit.pk],
            row_count=counts.get(unit.pk, 0),
        )
        for unit in units
        if needle in str(unit.name).lower()
        or any(needle in alias.lower() for alias in aliases[unit.pk])
    ]
    if unused_only:
        rows = [row for row in rows if not row.row_count]
    if by_added:
        return sorted(rows, key=lambda row: row.unit.pk)
    return sorted(rows, key=lambda row: (str(row.unit.name).lower(), row.owner_name))


def selected_units(unit_ids: Iterable[int]) -> list[UnitRow]:
    """The selected units as rows, in list order; unknown ids are ignored."""
    wanted = set(unit_ids)
    return [row for row in unit_rows() if row.unit.pk in wanted]


def rows_using_units(unit_ids: Iterable[int]) -> QuerySet:
    """Every user's ingredient rows pointing at any of `unit_ids`, trash included."""
    return IngredientInRecipe.objects.filter(unit__in=list(unit_ids))


def recipes_for_units(*, unit_ids: Iterable[int], owner: AbstractBaseUser) -> QuerySet:
    """`owner`'s live recipes with a row using any of `unit_ids`, A to Z."""
    return (
        Recipe.objects.live()
        .filter(owner=owner, ingredient_groups__items__unit__in=list(unit_ids))
        .distinct()
        .order_by(Lower("recipe_name"), "recipe_name")
    )


def _repoint(*, victim_ids: list[int], replacement: Unit | None) -> None:
    """Point every row of `victim_ids` at `replacement`, or keep each unit's name as text.

    Raises `UnitScopeError`, writing nothing, if `replacement` is private and a
    row is in another user's recipe.
    """
    rows = rows_using_units(victim_ids)
    if replacement is None:
        for unit in Unit.objects.filter(pk__in=victim_ids):
            rows.filter(unit=unit).update(unit=None, legacy_unit=unit.name)
        return
    if replacement.owner_id is not None:
        elsewhere = rows.exclude(ingredient_group__recipe__owner=replacement.owner_id)
        if elsewhere.exists():
            msg = (
                f"“{replacement.name}” is private to {replacement.owner}, and another "
                "user's recipe uses these units — promote it first, or pick a global one."
            )
            raise UnitScopeError(msg)
    rows.update(unit=replacement)


def _aliases_to(*, survivor: Unit, victim_ids: list[int], names: list[str]) -> None:
    """Give a global `survivor` the victims' aliases, and `names` as new ones.

    Call once the victims are gone, so their names are free. A name that is a
    global unit or already an alias is skipped: it means something already.
    """
    taken = {str(survivor.name).lower()}
    UnitAlias.objects.filter(unit__in=victim_ids, alias_name__iexact=survivor.name).delete()
    UnitAlias.objects.filter(unit__in=victim_ids).update(unit=survivor)
    for name in names:
        lowered = name.lower()
        if (
            lowered in taken
            or Unit.objects.filter(owner__isnull=True, name__iexact=name).exists()
            or UnitAlias.objects.filter(alias_name__iexact=name).exists()
        ):
            continue
        UnitAlias.objects.create(alias_name=name, unit=survivor)
        taken.add(lowered)


def _delete(unit_ids: list[int]) -> int:
    """Delete the units, their aliases with them; returns how many went."""
    units = Unit.objects.filter(pk__in=unit_ids)
    count = units.count()
    units.delete()
    return count


@transaction.atomic
def merge_units(*, survivor_id: int, victim_ids: Iterable[int], keep_aliases: bool) -> int:
    """Move every row of `victim_ids` onto `survivor_id`, then delete the victims.

    The survivor is never deleted, even when listed. With a global survivor,
    the victims' aliases move to it, and with `keep_aliases` their names become
    aliases too, so a user typing one again gets the survivor. Raises
    `UnitScopeError`, writing nothing, if the survivor is private and a
    victim's row is in another user's recipe. Returns how many units went.
    """
    survivor = Unit.objects.get(pk=survivor_id)
    victims = [pk for pk in dict.fromkeys(victim_ids) if pk != survivor_id]
    names = list(Unit.objects.filter(pk__in=victims).values_list("name", flat=True))
    _repoint(victim_ids=victims, replacement=survivor)
    if survivor.owner_id is None:
        # Moved before the delete, which would cascade them away.
        _aliases_to(survivor=survivor, victim_ids=victims, names=[])
    deleted = _delete(victims)
    if survivor.owner_id is None and keep_aliases:
        _aliases_to(survivor=survivor, victim_ids=[], names=names)
    return deleted


@transaction.atomic
def delete_units(*, unit_ids: Iterable[int], replacement_id: int | None = None) -> int:
    """Delete units; their rows move to `replacement_id`, or keep the name as text.

    The replacement is never deleted, even when selected. Aliases go with their
    unit. Raises `UnitScopeError`, writing nothing, as `merge_units` does.
    Returns how many units went.
    """
    victims = [pk for pk in dict.fromkeys(unit_ids) if pk != replacement_id]
    replacement = Unit.objects.get(pk=replacement_id) if replacement_id is not None else None
    _repoint(victim_ids=victims, replacement=replacement)
    return _delete(victims)


@transaction.atomic
def promote_units(unit_ids: Iterable[int], *, dimension: str) -> list[int]:
    """Make private units global, folding in every same-named private unit.

    For each selected private unit: if a global unit already has its name
    (ignoring case) it is merged into that one; otherwise it loses its owner
    and takes `dimension`. Either way every other user's private unit of that
    name is then merged in, so everyone's recipes share it. Global units in the
    selection are left as they are. Raises `ValueError`, writing nothing, when
    a new global unit needs a dimension and none is given.

    Returns the ids of the resulting global units, in selection order.
    """
    promoted: list[int] = []
    for unit in Unit.objects.filter(pk__in=list(unit_ids)).order_by("pk"):
        if not Unit.objects.filter(pk=unit.pk).exists():
            continue  # folded into an earlier selected unit of the same name
        name = cast(str, unit.name)
        same_name = Unit.objects.filter(name__iexact=name)
        target = same_name.filter(owner__isnull=True).first()
        if target is None:
            if not (unit.dimension or dimension):
                msg = f"Pick what “{name}” measures: a global unit needs a dimension."
                raise ValueError(msg)
            unit.owner = None
            unit.dimension = unit.dimension or dimension
            unit.save(update_fields=["owner", "dimension"])
            target = unit
        victims = list(same_name.filter(owner__isnull=False).values_list("pk", flat=True))
        delete_units(unit_ids=victims, replacement_id=target.pk)
        if target.pk not in promoted:
            promoted.append(target.pk)
    return promoted
