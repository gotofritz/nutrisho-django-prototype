"""Delete recipes by ID."""

from django.core.management.base import BaseCommand

from recipes.models.recipe import Recipe


class Command(BaseCommand):
    help = "Delete one or more recipes by ID"

    def add_arguments(self, parser):
        parser.add_argument(
            "--id",
            nargs="+",
            type=int,
            dest="ids",
            required=True,
            help="Recipe ID(s) to delete",
        )

    def handle(self, *args, **options):
        ids = options["ids"]
        qs = Recipe.objects.filter(pk__in=ids)
        count = qs.count()
        if count:
            qs.delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted {count} recipe(s) for id(s): {ids}"))
        else:
            self.stdout.write(self.style.WARNING(f"No recipes found for id(s): {ids}"))
