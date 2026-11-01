"""Query and mutation services for the staff cuisine tool (plan 011).

Pure ORM helpers with no HTTP concerns, like `ingredient_admin`, so the HTMX
views in `recipes/views/cuisine_admin.py` stay thin. `Recipe.cuisine` is
SET_NULL and `Cuisine.parent` is PROTECT, so a node with children is never
merged away or deleted here: its regions would have nowhere to go.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.db.models import Count, QuerySet
from django.db.models.functions import Lower

from recipes.models import Cuisine, Recipe
from recipes.models.cuisine import MAX_CUISINE_DEPTH, PATH_SEPARATOR


class CuisineHasChildrenError(Exception):
    """Raised when a merge or delete would leave a node's children without a parent."""


@dataclass(frozen=True)
class CuisineRow:
    """One line of the tool's list: the node, its path and how deep it sits."""

    cuisine: Cuisine
    path: str
    depth: int
    recipe_count: int


def cuisine_rows(query: str = "") -> list[CuisineRow]:
    """Every node whose path contains `query` (ignoring case), sorted by path.

    Paths are built in Python from one query, since the tree is a few hundred
    rows and SQLite has no convenient recursive path expression here.
    """
    nodes = {c.pk: c for c in Cuisine.objects.annotate(recipe_count=Count("recipe"))}
    rows = []
    for node in nodes.values():
        names = [str(node.cuisine)]
        parent_id = node.parent_id
        while parent_id in nodes and len(names) <= MAX_CUISINE_DEPTH:
            names.insert(0, str(nodes[parent_id].cuisine))
            parent_id = nodes[parent_id].parent_id
        path = PATH_SEPARATOR.join(names)
        if query.lower() in path.lower():
            rows.append(
                CuisineRow(
                    cuisine=node,
                    path=path,
                    depth=len(names) - 1,
                    recipe_count=node.recipe_count,
                )
            )
    return sorted(rows, key=lambda row: row.path.lower())


def selected_cuisines(cuisine_ids: Iterable[int]) -> list[CuisineRow]:
    """The selected nodes as rows, in list order; unknown ids are ignored."""
    wanted = set(cuisine_ids)
    return [row for row in cuisine_rows() if row.cuisine.pk in wanted]


def recipes_using_cuisines(cuisine_ids: Iterable[int]) -> QuerySet:
    """Every owner's recipes pointing at any of `cuisine_ids`."""
    return Recipe.objects.filter(cuisine__in=list(cuisine_ids)).order_by(
        Lower("recipe_name"), "recipe_name"
    )


def recipes_for_cuisines(*, cuisine_ids: Iterable[int], owner: AbstractBaseUser) -> QuerySet:
    """The owner's slice of `recipes_using_cuisines`, as in the ingredient tool."""
    return recipes_using_cuisines(cuisine_ids).filter(owner=owner)


def _refuse_parents(cuisine_ids: list[int]) -> None:
    parents = Cuisine.objects.filter(pk__in=cuisine_ids, children__isnull=False).distinct()
    names = ", ".join(sorted(str(c.cuisine) for c in parents))
    if names:
        msg = f"{names} still contains other cuisines — move, merge or delete those first."
        raise CuisineHasChildrenError(msg)


@transaction.atomic
def merge_cuisines(*, survivor_id: int, victim_ids: Iterable[int]) -> int:
    """Move every recipe of `victim_ids` onto `survivor_id`, then delete the victims.

    The survivor is never deleted, even when listed. Raises
    `CuisineHasChildrenError`, writing nothing, if a victim has children.
    Returns the number of nodes merged away.
    """
    victims = [pk for pk in dict.fromkeys(victim_ids) if pk != survivor_id]
    _refuse_parents(victims)
    Recipe.objects.filter(cuisine__in=victims).update(cuisine=survivor_id)
    deleted, _ = Cuisine.objects.filter(pk__in=victims).delete()
    return deleted


@transaction.atomic
def delete_cuisines(*, cuisine_ids: Iterable[int], replacement_id: int | None = None) -> int:
    """Delete nodes; their recipes move to `replacement_id`, or lose their cuisine.

    The replacement is never deleted, even when selected. Raises
    `CuisineHasChildrenError`, writing nothing, if a node has children.
    Returns the number of nodes deleted.
    """
    victims = [pk for pk in dict.fromkeys(cuisine_ids) if pk != replacement_id]
    _refuse_parents(victims)
    Recipe.objects.filter(cuisine__in=victims).update(cuisine=replacement_id)
    deleted, _ = Cuisine.objects.filter(pk__in=victims).delete()
    return deleted
