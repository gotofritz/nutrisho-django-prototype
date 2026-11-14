"""Write a recipe's ingredient groups and rows: create, save, delete, move, reassign (#77).

Two rules hold across them. A group left with no rows goes, except a recipe's
last group, which stays empty or not: the "+ Add ingredient" button lives
inside a group block, so a recipe with no groups could only be refilled by
adding a group first. And once a recipe has more than one group, each needs a
name, checked with the recipe locked so two tabs cannot both add a blank one.

A refusal is raised once the transaction has closed, never inside it: nothing
has been written by then, so there is nothing to roll back.

Each function takes a recipe its caller has already checked the user owns, and
touches only that recipe's groups and rows.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Literal

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Max

from recipes.models import IngredientGroup, IngredientInRecipe, Recipe
from recipes.services.name_resolution import resolve_ingredient
from recipes.utils.sequencing import insert_at_index, move_in_sequence, remove_and_compact

_GROUP_NAME_MAX_LENGTH = IngredientGroup._meta.get_field("group_name").max_length  # ty: ignore[unresolved-attribute]  # no Django stubs


# Every row field the inline editor writes; never its group or position.
_ROW_FIELDS = ["quantity", "unit", "legacy_unit", "preparation", "note", "ingredient", "substitute"]


class GroupNameError(ValueError):
    """A group needs a name once its recipe has more than one."""

    def __init__(self) -> None:
        """Carry the message the group form shows."""
        super().__init__("Group name required when multiple groups exist.")


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


def _check_group_name(name: str, *, group_count: int) -> str | None:
    """`name` trimmed, or None when it may not be blank: only a recipe's one group may."""
    name = name.strip()
    if group_count > 1 and not name:
        return None
    return name


def _gone(what: str) -> ObjectDoesNotExist:
    return ObjectDoesNotExist(f"The {what} has been deleted.")


def create_group(*, recipe: Recipe, name: str, position: str | None = None) -> IngredientGroup:
    """Add a group at `position` (a page position, as `insert_at_index` takes it).

    Raises `GroupNameError`, or `ObjectDoesNotExist` when the recipe has gone.
    """
    group: IngredientGroup | None = None
    with transaction.atomic():
        if not _lock_recipe(recipe):
            raise _gone("recipe")
        count = IngredientGroup.objects.filter(recipe=recipe).count()
        checked = _check_group_name(name, group_count=count + 1)
        if checked is not None:
            group = IngredientGroup(recipe=recipe, group_name=checked)
            insert_at_index(
                siblings=IngredientGroup.objects.filter(recipe=recipe),
                instance=group,
                requested_index=position,
            )
    if group is None:
        raise GroupNameError
    return group


def rename_group(*, recipe: Recipe, group_id: int, name: str) -> IngredientGroup:
    """Rename a group.

    Raises `GroupNameError`, or `ObjectDoesNotExist` when the group has gone.
    """
    checked: str | None = None
    with transaction.atomic():
        _lock_recipe(recipe)
        group = (
            IngredientGroup.objects.select_for_update().filter(pk=group_id, recipe=recipe).first()
        )
        if group is not None:
            count = IngredientGroup.objects.filter(recipe=recipe).count()
            checked = _check_group_name(name, group_count=count)
            if checked is not None:
                group.group_name = checked
                group.save(update_fields=["group_name"])
    if group is None:
        raise _gone("group")
    if checked is None:
        raise GroupNameError
    return group


def resolve_row_names(
    row: IngredientInRecipe,
    *,
    owner: AbstractBaseUser,
    ingredient_name: str,
    substitute_name: str = "",
) -> None:
    """Point `row` at the named ingredient and substitute, creating either if new.

    Names resolve within `owner`'s vocabulary, and a blank substitute clears it.
    Call inside the write's transaction, before saving the row.
    """
    row.ingredient = resolve_ingredient(ingredient_name.strip(), owner=owner)  # ty: ignore[invalid-assignment]  # FK descriptor
    substitute_name = substitute_name.strip()
    row.substitute = (  # ty: ignore[invalid-assignment]  # FK descriptor
        resolve_ingredient(substitute_name, owner=owner) if substitute_name else None
    )


def create_row(
    *,
    recipe: Recipe,
    group_id: int,
    row: IngredientInRecipe,
    ingredient_name: str,
    substitute_name: str = "",
    position: str | None = None,
) -> IngredientInRecipe:
    """Add `row`, its own fields already set, to a group at `position`.

    `ObjectDoesNotExist` when the group has gone; no ingredient is made for it.
    """
    with transaction.atomic():
        group = (
            IngredientGroup.objects.select_for_update().filter(pk=group_id, recipe=recipe).first()
        )
        if group is not None:
            resolve_row_names(
                row,
                owner=recipe.owner,
                ingredient_name=ingredient_name,
                substitute_name=substitute_name,
            )
            row.ingredient_group = group
            insert_at_index(
                siblings=IngredientInRecipe.objects.filter(ingredient_group=group),
                instance=row,
                requested_index=position,
            )
    if group is None:
        raise _gone("group")
    return row


def save_row(
    *,
    recipe: Recipe,
    row: IngredientInRecipe,
    ingredient_name: str,
    substitute_name: str = "",
) -> None:
    """Save `row`'s own fields and names, never its group or position.

    A reassign or move since the form opened is kept. `ObjectDoesNotExist` when
    the row has gone.
    """
    with transaction.atomic():
        found = (
            IngredientInRecipe.objects.select_for_update()
            .filter(pk=row.pk, ingredient_group__recipe=recipe)
            .exists()
        )
        if found:
            resolve_row_names(
                row,
                owner=recipe.owner,
                ingredient_name=ingredient_name,
                substitute_name=substitute_name,
            )
            row.save(update_fields=_ROW_FIELDS)
    if not found:
        raise _gone("ingredient")


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
