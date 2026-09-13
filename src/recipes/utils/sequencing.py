"""Sequencing helpers for index_in_sequence-ordered rows."""

from typing import Literal, Protocol

from django.db import models, transaction


class Sequenced(Protocol):
    """Model row ordered by an index_in_sequence column."""

    pk: int | None
    index_in_sequence: int

    def save(self) -> None: ...

    def delete(self) -> object: ...


@transaction.atomic
def insert_at_index(
    *,
    siblings: models.QuerySet,
    instance: Sequenced,
    requested_index: str | None,
    lock_parent: models.QuerySet | None = None,
) -> None:
    """Save instance into siblings' index_in_sequence ordering.

    requested_index is the row's 0-based position as seen in the client DOM,
    not a raw index_in_sequence value: sibling indexes may be 1-based or have
    gaps (the YAML importer seeds 1-based sequences), so the target slot is
    resolved against the ordered sibling list. The DOM position may also count
    unsaved sibling drafts, so it is clamped to the list length; missing or
    non-numeric values append.

    Siblings are locked with select_for_update before the insertion window
    is computed so concurrent creates into the same parent serialize instead
    of racing on the unique (parent, index_in_sequence) constraint. (On
    SQLite this is a no-op; its single-writer locking serializes anyway.)

    lock_parent, if given, is locked first so that concurrent "first insert"
    requests (where siblings is empty and select_for_update locks nothing)
    still serialize correctly.
    """
    if lock_parent is not None:
        list(lock_parent.select_for_update().values("pk"))
    rows = list(siblings.select_for_update().order_by("index_in_sequence"))
    try:
        position = int(requested_index)  # ty: ignore[invalid-argument-type]  # ValueError/TypeError handled
    except TypeError, ValueError:
        position = len(rows)
    position = max(0, min(position, len(rows)))
    if position == len(rows):
        instance.index_in_sequence = (rows[-1].index_in_sequence + 1) if rows else 0
    else:
        # Take over the index of the row currently at this position and
        # shift it and everything after up by one (descending, to satisfy
        # the unique constraint).
        target_index = rows[position].index_in_sequence
        for row in reversed(rows[position:]):
            row.index_in_sequence += 1
            row.save()
        instance.index_in_sequence = target_index
    instance.save()


@transaction.atomic
def remove_and_compact(*, siblings: models.QuerySet, instance: Sequenced) -> None:
    """Delete instance and close the index_in_sequence gap it leaves."""
    rows = list(siblings.select_for_update().order_by("index_in_sequence"))
    fresh = next((r for r in rows if r.pk == instance.pk), None)
    if fresh is None:
        return
    deleted_index = fresh.index_in_sequence
    instance.delete()
    for row in rows:
        if row.index_in_sequence > deleted_index:
            row.index_in_sequence -= 1
            row.save()


@transaction.atomic
def move_in_sequence(
    *,
    siblings: models.QuerySet,
    instance: Sequenced,
    direction: Literal["up", "down"],
) -> None:
    """Swap instance with its previous/next sibling; no-op at the edges.

    The swap goes through a -1 sentinel because SQLite checks the unique
    (parent, index_in_sequence) constraint per statement.
    """
    # Lock the full sibling set before reading neighbors so concurrent moves
    # on the same parent serialize rather than racing on the unique constraint.
    rows = list(siblings.select_for_update().order_by("index_in_sequence"))
    fresh = next((r for r in rows if r.pk == instance.pk), None)
    if fresh is None:
        return
    current_index = fresh.index_in_sequence
    if direction == "up":
        neighbor = next((r for r in reversed(rows) if r.index_in_sequence < current_index), None)
    else:
        neighbor = next((r for r in rows if r.index_in_sequence > current_index), None)
    if neighbor is None:
        return
    idx_a, idx_b = current_index, neighbor.index_in_sequence
    siblings.filter(pk=instance.pk).update(index_in_sequence=-1)
    siblings.filter(pk=neighbor.pk).update(index_in_sequence=idx_a)
    siblings.filter(pk=instance.pk).update(index_in_sequence=idx_b)
