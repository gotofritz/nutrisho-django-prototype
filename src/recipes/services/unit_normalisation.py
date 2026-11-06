"""Move the free-text units typed before #67 onto the unit vocabulary.

`plan_unit_normalisation` reads every distinct `legacy_unit` value and says what
it becomes: a canonical `Unit` (`Tbsp`, `tbs`, `cloves`), a word for
`preparation` (`small`) or the `note` (`to taste`, whose quantity is dropped
because scaling would multiply it), or unknown. `apply_unit_plan` writes that
plan. Unknown values stay as typed, still shown on the page, until staff add an
alias in admin or fix the row; re-running picks them up. The
`normalise_units` command is the reviewed front end: a dry run unless told to
apply.
"""

from dataclasses import dataclass, field

from django.db import transaction

from recipes.models import IngredientInRecipe, Unit
from recipes.services.name_resolution import find_unit
from recipes.utils.unit_words import append_text, not_a_unit


@dataclass(frozen=True)
class UnitPlanEntry:
    """What one distinct legacy value becomes, and how many rows carry it."""

    value: str
    rows: int
    unit: Unit | None
    field: str | None  # "preparation" or "note" for a word that is not a unit

    @property
    def known(self) -> bool:
        """Whether applying the plan does anything for this value."""
        return self.unit is not None or self.field is not None


@dataclass
class UnitPlanResult:
    """What applying a plan wrote."""

    updated: int = 0
    quantities_cleared: int = 0
    skipped: list[int] = field(default_factory=list)  # rows a longer text would overflow
    unknown: list[str] = field(default_factory=list)


def plan_unit_normalisation() -> list[UnitPlanEntry]:
    """One entry per distinct `legacy_unit` value, most used first. Reads only."""
    counts: dict[str, int] = {}
    for value in IngredientInRecipe.objects.exclude(legacy_unit="").values_list(
        "legacy_unit", flat=True
    ):
        counts[value] = counts.get(value, 0) + 1
    entries = []
    for value, rows in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        unit = find_unit(value)
        entries.append(
            UnitPlanEntry(
                value=value,
                rows=rows,
                unit=unit,
                field=None if unit is not None else not_a_unit(value),
            )
        )
    return entries


def apply_unit_plan(plan: list[UnitPlanEntry]) -> UnitPlanResult:
    """Write `plan` in one transaction; rows changed since it was made are left alone."""
    result = UnitPlanResult(unknown=[entry.value for entry in plan if not entry.known])
    with transaction.atomic():
        for entry in plan:
            if not entry.known:
                continue
            for row in IngredientInRecipe.objects.filter(legacy_unit=entry.value):
                if not _apply_entry(row, entry):
                    result.skipped.append(row.pk)
                    continue
                if entry.field == "note" and row.quantity is not None:
                    row.quantity = None
                    result.quantities_cleared += 1
                row.save(update_fields=["unit", "legacy_unit", "preparation", "note", "quantity"])
                result.updated += 1
    return result


def _apply_entry(row: IngredientInRecipe, entry: UnitPlanEntry) -> bool:
    """Change `row` in memory as `entry` says; False if the text would not fit."""
    if entry.unit is not None:
        row.unit = entry.unit  # ty: ignore[invalid-assignment]  # FK descriptor
    else:
        name = str(entry.field)
        word = " ".join(entry.value.lower().split())
        text = append_text(getattr(row, name), word)
        if len(text) > IngredientInRecipe._meta.get_field(name).max_length:  # ty: ignore[unresolved-attribute]  # no Django stubs
            return False
        setattr(row, name, text)
    row.legacy_unit = ""  # ty: ignore[invalid-assignment]  # CharField descriptor
    return True
