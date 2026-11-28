"""Review, then add, common synonyms as ingredient aliases (#203).

A dry run by default: it lists each alias the curated list would add, what it
would mean and how many ingredient rows of that name it would fold in.
`--apply` writes that plan as one change in the ingredient tool's history, so
its Undo can take the whole run back.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from recipes.services.ingredient_journal import journaled
from recipes.services.ingredient_synonyms import (
    SynonymPlanEntry,
    apply_synonym_aliases,
    plan_synonym_aliases,
)


def _plural(count: int, singular: str, plural: str = "") -> str:
    return f"{count} {singular if count == 1 else plural or singular + 's'}"


def _line(entry: SynonymPlanEntry) -> str:
    line = f"{entry.alias} → {entry.canonical}"
    if entry.clash:
        return f"{line}: left alone, {entry.clash}"
    if entry.merges:
        return f"{line}, merging {_plural(entry.merges, 'ingredient row')}"
    return line


class Command(BaseCommand):
    help = "List common synonyms to add as ingredient aliases; --apply adds them"

    def add_arguments(self, parser):  # noqa: D102 - BaseCommand API
        parser.add_argument(
            "--apply", action="store_true", help="add the aliases instead of only listing them"
        )

    def handle(self, *args, **options):
        """Print the plan, and apply it with --apply."""
        plan = plan_synonym_aliases()
        if not plan:
            self.stdout.write(self.style.SUCCESS("No synonyms to add."))
            return
        for entry in plan:
            self.stdout.write(_line(entry))
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Dry run: nothing written. Re-run with --apply."))
            return
        owner = get_user_model().objects.filter(is_superuser=True).order_by("pk").first()
        if owner is None:
            msg = "No superuser to record the change as: run make bootstrap first."
            raise CommandError(msg)
        with journaled(user=owner) as journal:
            added = apply_synonym_aliases(plan, journal=journal)
        self.stdout.write(self.style.SUCCESS(f"Added {_plural(added, 'alias', 'aliases')}."))
