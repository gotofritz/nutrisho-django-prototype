"""Delete recipes by ID."""

import uuid

from django.core.management.base import BaseCommand

from recipes.models.recipe import Recipe


class Command(BaseCommand):
    help = "Delete one or more recipes by ID"

    def add_arguments(self, parser):
        """Register command-line arguments."""
        parser.add_argument(
            "--id",
            nargs="+",
            type=uuid.UUID,
            dest="ids",
            required=True,
            help="Recipe ID(s) to delete, as shown in the recipe's address",
        )

    def handle(self, *args, **options):
        """Delete the recipes with the given IDs."""
        ids = options["ids"]
        qs = Recipe.objects.filter(pk__in=ids)
        count = qs.count()
        if count:
            qs.delete()
            self.stdout.write(
                self.style.SUCCESS(f"Deleted {count} recipe(s) for id(s): {_shown(ids)}")
            )
        else:
            self.stdout.write(self.style.WARNING(f"No recipes found for id(s): {_shown(ids)}"))


def _shown(ids: list[uuid.UUID]) -> str:
    return ", ".join(str(i) for i in ids)
