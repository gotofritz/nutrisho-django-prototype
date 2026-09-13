"""Report Ingredient rows whose names differ only by case.

Run this before applying the `ingredient_name_ci_unique` constraint: merge
whatever it reports with the clean-up tool at /recipes/ingredients/manage/,
then migrate.
"""

from django.core.management.base import BaseCommand

from recipes.services.ingredient_admin import find_ingredient_duplicates


class Command(BaseCommand):
    help = "List ingredients whose names differ only by case, so they can be merged"

    def handle(self, *args, **options):
        groups = find_ingredient_duplicates()
        if not groups:
            self.stdout.write(self.style.SUCCESS("No case-insensitive duplicates found."))
            return
        for group in groups:
            names = ", ".join(f"{i.ingredient_name} (id={i.pk})" for i in group)
            self.stdout.write(names)
        plural = "" if len(groups) == 1 else "s"
        self.stdout.write(
            self.style.WARNING(
                f"{len(groups)} duplicate group{plural} — merge them at "
                "/recipes/ingredients/manage/ before migrating."
            )
        )
