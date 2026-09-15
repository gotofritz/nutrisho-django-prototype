"""Report `Ingredient` rows that are the same ingredient written two ways.

Two classes, both merged with the clean-up tool at
/recipes/ingredients/manage/:

- **case** — `Onion` / `onion`. Run this before applying the
  `ingredient_name_ci_unique` constraint: merge whatever it reports, then migrate.
- **singular/plural** — `onion` / `onions`. A plural is the display form of one
  ingredient at a quantity other than 1 (issue #24), never a second row, so the
  plural row is bad data. Merging it into the singular loses nothing: the recipe
  page adds the "s" back wherever the quantity calls for it.
"""

from django.core.management.base import BaseCommand

from recipes.services.ingredient_admin import find_ingredient_duplicates, find_plural_duplicates

_MERGE_AT = "/recipes/ingredients/manage/"


class Command(BaseCommand):
    help = "List ingredients that differ only by case, or only by plural, so they can be merged"

    def _list(self, groups: list[list]) -> None:
        for group in groups:
            self.stdout.write(", ".join(f"{i.ingredient_name} (id={i.pk})" for i in group))

    def handle(self, *args, **options):
        case_groups = find_ingredient_duplicates()
        if case_groups:
            self._list(case_groups)
            plural = "" if len(case_groups) == 1 else "s"
            self.stdout.write(
                self.style.WARNING(
                    f"{len(case_groups)} duplicate group{plural} — merge them at "
                    f"{_MERGE_AT} before migrating."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("No case-insensitive duplicates found."))

        plural_groups = find_plural_duplicates()
        if plural_groups:
            self._list(plural_groups)
            plural = "" if len(plural_groups) == 1 else "s"
            self.stdout.write(
                self.style.WARNING(
                    f"{len(plural_groups)} singular/plural pair{plural} — merge each into "
                    f"the singular at {_MERGE_AT}; the display adds the plural."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("No singular/plural pairs found."))
