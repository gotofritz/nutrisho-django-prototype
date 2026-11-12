"""Write a recipe's ingredient groups and rows: delete, move, reassign, prune (#77).

The rule they share: a group left with no rows goes, except a recipe's last
group, which stays empty or not. The "+ Add ingredient" button lives inside a
group block, so a recipe with no groups could only be refilled by adding a
group first.

Each function takes a recipe its caller has already checked the user owns, and
touches only that recipe's groups and rows.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Literal

from django.db import transaction
from django.db.models import Max

from recipes.models import IngredientGroup, IngredientInRecipe, Recipe
from recipes.utils.sequencing import move_in_sequence, remove_and_compact

_GROUP_NAME_MAX_LENGTH = IngredientGroup._meta.get_field("group_name").max_length  # ty: ignore[unresolved-attribute]  # no Django stubs


class ReassignError(ValueError):
    """The rows cannot be moved where they were asked to go."""


@dataclass(frozen=True)
class RowDeletion:
    """What deleting a row did to its group."""

    group_id: int
    group_pruned: bool


class GroupDeletion(Enum):
    """The outcome of `delete_group`."""

    DELETED = auto()
    MISSING = auto()
    KEPT_LAST = auto()


def _lock_recipe(recipe: Recipe) -> bool:
    """Lock the recipe row; False when it has gone."""
    return bool(list(Recipe.objects.filter(pk=recipe.pk).select_for_update().values("pk")))


def prune_empty_group(*, recipe: Recipe, group: IngredientGroup) -> bool:
    """Drop `group` if nothing is left in it; return whether it went.

    Call inside the caller's transaction: it reads the group's row count and
    then deletes, and `remove_and_compact` closes the index gap it leaves.
    """
    if IngredientInRecipe.objects.filter(ingredient_group=group).exists():
        return False
    if IngredientGroup.objects.filter(recipe=recipe).count() < 2:
        return False
    remove_and_compact(siblings=IngredientGroup.objects.filter(recipe=recipe), instance=group)
    return True


def delete_row(*, recipe: Recipe, row_id: int) -> RowDeletion | None:
    """Delete a row, closing its group's gap and pruning the group if emptied.

    None when the row is not (or no longer) in the recipe.
    """
    with transaction.atomic():
        row = (
            IngredientInRecipe.objects.select_for_update()
            .select_related("ingredient_group")
            .filter(pk=row_id, ingredient_group__recipe=recipe)
            .first()
        )
        if row is None:
            return None
        group = row.ingredient_group
        group_id = group.pk  # deleting clears pk on the instance
        remove_and_compact(
            siblings=IngredientInRecipe.objects.filter(ingredient_group=group), instance=row
        )
        pruned = prune_empty_group(recipe=recipe, group=group)
    return RowDeletion(group_id=group_id, group_pruned=pruned)


def delete_group(*, recipe: Recipe, group_id: int) -> GroupDeletion:
    """Delete a group and its rows, unless it is the recipe's last group."""
    with transaction.atomic():
        # Lock the recipe so two tabs cannot each delete one of its last two groups.
        _lock_recipe(recipe)
        group = IngredientGroup.objects.filter(pk=group_id, recipe=recipe).first()
        if group is None:
            return GroupDeletion.MISSING
        if IngredientGroup.objects.filter(recipe=recipe).count() < 2:
            return GroupDeletion.KEPT_LAST
        remove_and_compact(siblings=IngredientGroup.objects.filter(recipe=recipe), instance=group)
    return GroupDeletion.DELETED


def move_row(
    *, recipe: Recipe, row_id: int, direction: Literal["up", "down"]
) -> IngredientGroup | None:
    """Swap a row with its neighbour in its group; return that group.

    The group is read fresh under the lock, so it may differ from the one the
    page showed if a reassign moved the row meanwhile. None when the row has gone.
    """
    with transaction.atomic():
        row = (
            IngredientInRecipe.objects.select_for_update()
            .select_related("ingredient_group")
            .filter(pk=row_id, ingredient_group__recipe=recipe)
            .first()
        )
        if row is None:
            return None
        group = row.ingredient_group
        move_in_sequence(
            siblings=IngredientInRecipe.objects.filter(ingredient_group=group),
            instance=row,
            direction=direction,
        )
    return group


def _new_group_at_end(*, recipe: Recipe, name: str) -> IngredientGroup:
    name = name.strip()
    if not name or len(name) > _GROUP_NAME_MAX_LENGTH:
        msg = "Group name is required."
        raise ReassignError(msg)
    last = IngredientGroup.objects.filter(recipe=recipe).aggregate(Max("index_in_sequence"))[
        "index_in_sequence__max"
    ]
    return IngredientGroup.objects.create(
        recipe=recipe,
        group_name=name,
        index_in_sequence=(last + 1) if last is not None else 0,
    )


def reassign_rows(
    *,
    recipe: Recipe,
    row_ids: list[int],
    target_group_id: int | None,
    new_group_name: str = "",
) -> None:
    """Move rows into another group, keeping the order the page showed them in.

    `target_group_id` None moves them into a new group named `new_group_name`,
    appended after the others. Ids outside the recipe are ignored, and moving
    nothing, or only rows already in the target, changes nothing. Source groups
    left empty are pruned. Raises `ReassignError` for a target outside the
    recipe or a blank new group name.
    """
    with transaction.atomic():
        # Lock the recipe first so concurrent creates, deletes and reorders of its
        # groups serialise, and the target is read fresh after them.
        _lock_recipe(recipe)
        target: IngredientGroup | None = None
        if target_group_id is not None:
            target = (
                IngredientGroup.objects.select_for_update()
                .filter(id=target_group_id, recipe=recipe)
                .first()
            )
            if target is None:
                msg = "Invalid group."
                raise ReassignError(msg)

        selected = list(
            IngredientInRecipe.objects.filter(id__in=row_ids, ingredient_group__recipe=recipe)
        )
        if not selected:
            return
        if target is not None and all(r.ingredient_group_id == target.pk for r in selected):
            # Moving would only reorder rows to the end, so do nothing.
            return
        if target is None:
            target = _new_group_at_end(recipe=recipe, name=new_group_name)
            created = True
        else:
            created = False

        # Lock every row in the recipe before reading or writing, so concurrent
        # reassigns and moves serialise rather than race on the unique constraint.
        list(
            IngredientInRecipe.objects.filter(ingredient_group__recipe=recipe)
            .select_for_update()
            .values("pk")
            .order_by("ingredient_group_id", "index_in_sequence")
        )
        # Re-read after locking: the rows read above may be stale.
        moving = list(
            IngredientInRecipe.objects.filter(id__in=[r.pk for r in selected])
            .select_related("ingredient_group")
            .order_by("ingredient_group__index_in_sequence", "index_in_sequence")
        )
        if not moving:
            # Every selected row was deleted meanwhile; drop the group made for them.
            if created:
                target.delete()
            return
        _merge_into(recipe=recipe, target=target, moving=moving)


def _merge_into(
    *, recipe: Recipe, target: IngredientGroup, moving: list[IngredientInRecipe]
) -> None:
    """Write `moving` into `target`, interleaved with its rows by page order."""
    moving_ids = [r.pk for r in moving]
    source_ids = {r.ingredient_group_id for r in moving if r.ingredient_group_id != target.pk}
    staying = list(
        IngredientInRecipe.objects.filter(ingredient_group=target)
        .exclude(id__in=moving_ids)
        .order_by("index_in_sequence")
    )

    # Page order before the move: group position first, then row position.
    keyed = [
        (r.ingredient_group.index_in_sequence, r.index_in_sequence, r)  # ty: ignore[unresolved-attribute]  # FK descriptor
        for r in moving
    ]
    keyed.extend((target.index_in_sequence, r.index_in_sequence, r) for r in staying)
    keyed.sort(key=lambda k: (k[0], k[1]))
    final_order = [k[2] for k in keyed]

    # Park every row bound for the target at a negative index to free the slots
    # before writing the merged order.
    for i, row in enumerate(moving + staying):
        row.ingredient_group = target
        row.index_in_sequence = -(i + 1)
        row.save(update_fields=["ingredient_group", "index_in_sequence"])

    # Close the gaps in the source groups; the target is rewritten below.
    emptied: list[IngredientGroup] = []
    for group_id in source_ids:
        remaining = list(
            IngredientInRecipe.objects.filter(ingredient_group_id=group_id).order_by(
                "index_in_sequence"
            )
        )
        if not remaining:
            source = IngredientGroup.objects.filter(pk=group_id).first()
            if source is not None:
                emptied.append(source)
            continue
        for i, row in enumerate(remaining):
            if row.index_in_sequence != i:
                row.index_in_sequence = i
                row.save(update_fields=["index_in_sequence"])

    for i, row in enumerate(final_order):
        row.index_in_sequence = i  # ty: ignore[invalid-assignment]  # no Django stubs
        row.save(update_fields=["ingredient_group", "index_in_sequence"])

    for source in emptied:
        prune_empty_group(recipe=recipe, group=source)
