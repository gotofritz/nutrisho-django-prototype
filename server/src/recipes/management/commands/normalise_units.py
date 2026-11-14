"""Review, then move, the free-text units typed before #67 onto the vocabulary.

A dry run by default: it lists every distinct legacy value, how many rows carry
it and what it would become. `--apply` writes that plan. Values it does not
know are left as typed; add an alias for them in Django admin (Unit aliases),
or fix the rows in the editor, and run it again.
"""

from django.core.management.base import BaseCommand

from recipes.services.unit_normalisation import (
    UnitPlanEntry,
    apply_unit_plan,
    plan_unit_normalisation,
)


def _plural(count: int, singular: str, plural: str = "") -> str:
    return f"{count} {singular if count == 1 else plural or singular + 's'}"


def _action(entry: UnitPlanEntry) -> str:
    if entry.unit is not None:
        return f"→ {entry.unit}"
    if entry.field == "note":
        return "→ note, quantity dropped"
    if entry.field is not None:
        return f"→ {entry.field}"
    return "unknown, left as typed"


class Command(BaseCommand):
    help = "List legacy free-text units and what each becomes; --apply writes it"

    def add_arguments(self, parser):  # noqa: D102 - BaseCommand API
        parser.add_argument(
            "--apply", action="store_true", help="write the plan instead of only listing it"
        )

    def handle(self, *args, **options):
        """Print the plan, and apply it with --apply."""
        plan = plan_unit_normalisation()
        if not plan:
            self.stdout.write(self.style.SUCCESS("No legacy units left."))
            return
        width = max(len(repr(entry.value)) for entry in plan)
        for entry in plan:
            self.stdout.write(f"{entry.value!r:<{width}}  {entry.rows:>5}  {_action(entry)}")
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Dry run: nothing written. Re-run with --apply."))
            return
        result = apply_unit_plan(plan)
        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {_plural(result.updated, 'row')}, "
                f"{_plural(result.quantities_cleared, 'quantity', 'quantities')} cleared."
            )
        )
        if result.skipped:
            ids = ", ".join(str(pk) for pk in result.skipped)
            self.stdout.write(
                self.style.WARNING(
                    f"Skipped {_plural(len(result.skipped), 'row')} with no room left in "
                    f"preparation or note (ids {ids}); edit them by hand."
                )
            )
        if result.unknown:
            self.stdout.write(
                self.style.WARNING(
                    f"{_plural(len(result.unknown), 'value')} left as typed: add a unit alias "
                    "in admin, or edit the rows, then run this again."
                )
            )
