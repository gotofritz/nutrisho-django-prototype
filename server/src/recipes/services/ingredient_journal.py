"""Record the clean-up tool's changes to shared ingredients, and undo them (#75).

A merge or delete rewrites recipes every user owns, so each action runs inside
`journaled()`, which hands the services a `Journal`. The services note each
step just before they write it: rows about to be deleted (serialised whole),
foreign keys about to be repointed (row by row, with the old target), rows
created, and fields about to change. On success the steps are saved as one
`IngredientChange`; on failure the transaction takes the record with it.

`undo_change` replays the steps backwards. Only the newest change still in
force can be undone, so later changes never stand on rows an undo takes back.
A repointed recipe row goes back only if it still points where the change
left it: a row edited since keeps its edit.
"""

import json
from collections import defaultdict
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, cast

from django.apps import apps
from django.contrib.auth.models import AbstractBaseUser
from django.core import serializers
from django.db import IntegrityError, transaction
from django.db.models import Model, QuerySet
from django.utils import timezone

from recipes.models import Ingredient, IngredientChange

_SUMMARY_MAX = 500  # IngredientChange.summary max_length


class UndoError(Exception):
    """The change cannot be undone; nothing was written."""


class Journal:
    """The steps of one change, in the order they were written."""

    def __init__(self) -> None:
        """Start empty: a change that writes nothing records nothing."""
        self.events: list[dict[str, Any]] = []
        self.summary = ""

    def describe(self, text: str) -> None:
        """Say what the change did. The outermost service speaks first and wins."""
        if not self.summary:
            self.summary = text[:_SUMMARY_MAX]

    def deleted(self, queryset: QuerySet) -> None:
        """Note the rows `queryset` holds, about to be deleted."""
        rows = json.loads(serializers.serialize("json", queryset.order_by("pk")))
        if rows:
            self.events.append({"op": "deleted", "rows": rows})

    def repointed(self, queryset: QuerySet, *, field: str, to: int) -> None:
        """Note each row's `field` before `queryset` is updated to point at `to`."""
        rows = [[pk, old] for pk, old in queryset.values_list("pk", field) if old != to]
        if rows:
            self.events.append(
                {
                    "op": "repointed",
                    "model": _label(cast("type[Model]", queryset.model)),
                    "field": field,
                    "to": to,
                }
                | {"rows": rows}
            )

    def created(self, row: Model) -> None:
        """Note a row just created."""
        self.events.append({"op": "created", "model": _label(type(row)), "pk": row.pk})

    def updated(self, row: Model, *, fields: list[str]) -> None:
        """Note `fields` of `row` as they are now, about to be changed and saved."""
        meta = row._meta  # ty: ignore[unresolved-attribute]  # no Django stubs
        old = {name: getattr(row, meta.get_field(name).attname) for name in fields}
        self.events.append(
            {"op": "updated", "model": _label(type(row)), "pk": row.pk} | {"fields": old}
        )


def _label(model: type[Model]) -> str:
    return model._meta.label_lower  # ty: ignore[unresolved-attribute]  # no Django stubs


@contextmanager
def journaled(*, user: AbstractBaseUser) -> Generator[Journal]:
    """Run a change in one transaction and save what it wrote as an `IngredientChange`."""
    journal = Journal()
    with transaction.atomic():
        yield journal
        if journal.events:
            IngredientChange.objects.create(
                user=user, summary=journal.summary, events=journal.events
            )


def quoted(names: list[str]) -> str:
    """“a”, “b” — names as the summaries show them."""
    return ", ".join(f"“{name}”" for name in names)


def recent_changes(limit: int = 5) -> list[IngredientChange]:
    """The newest changes, newest first."""
    return list(IngredientChange.objects.select_related("user").order_by("-pk")[:limit])


def undoable_change() -> IngredientChange | None:
    """The one change Undo can take back: the newest not yet undone."""
    return IngredientChange.objects.filter(undone_at__isnull=True).order_by("-pk").first()


def undo_change(*, change_id: int) -> list[int]:
    """Take back change `change_id`, returning the ids of the ingredients it restored.

    Raises `UndoError` when it is not the newest change still in force, or when
    a row it would bring back clashes with one made since. Nothing is written
    then.
    """
    with transaction.atomic():
        change = undoable_change()
        if change is None or change.pk != change_id:
            msg = "Only the most recent change can be undone."
            raise UndoError(msg)
        restored: list[int] = []
        for event in reversed(cast("list[dict[str, Any]]", change.events)):
            restored += _UNDO[event["op"]](event)
        change.undone_at = timezone.now()
        change.save(update_fields=["undone_at"])
    return restored


def _undo_deleted(event: dict[str, Any]) -> list[int]:
    restored: list[int] = []
    for obj in serializers.deserialize("python", event["rows"]):
        try:
            with transaction.atomic():
                obj.save()
        except IntegrityError as exc:
            msg = f"“{obj.object}” exists again. Rename or merge it, then undo."
            raise UndoError(msg) from exc
        if isinstance(obj.object, Ingredient):
            restored.append(obj.object.pk)
    return restored


def _undo_repointed(event: dict[str, Any]) -> list[int]:
    model = apps.get_model(event["model"])
    field = event["field"]
    by_old: dict[int, list[int]] = defaultdict(list)
    for pk, old in event["rows"]:
        by_old[old].append(pk)
    for old, pks in by_old.items():
        model.objects.filter(pk__in=pks, **{field: event["to"]}).update(**{field: old})
    return []


def _undo_created(event: dict[str, Any]) -> list[int]:
    apps.get_model(event["model"]).objects.filter(pk=event["pk"]).delete()
    return []


def _undo_updated(event: dict[str, Any]) -> list[int]:
    apps.get_model(event["model"]).objects.filter(pk=event["pk"]).update(**event["fields"])
    return []


_UNDO: dict[str, Callable[[dict[str, Any]], list[int]]] = {
    "deleted": _undo_deleted,
    "repointed": _undo_repointed,
    "created": _undo_created,
    "updated": _undo_updated,
}
