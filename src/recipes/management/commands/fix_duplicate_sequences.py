"""Deduplicate IngredientGroup and IngredientInRecipe sequence indexes.

Run this before applying migration 0007 if your database has duplicate
index_in_sequence values. Duplicate rows are reassigned sequential indexes
within their group; no rows are deleted.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from recipes.models import IngredientGroup, IngredientInRecipe


class Command(BaseCommand):
    help = "Fix duplicate index_in_sequence values in IngredientGroup and IngredientInRecipe"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report duplicates without modifying the database",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write("DRY RUN — no changes will be written\n")

        group_fixes = self._fix_ingredient_groups(dry_run)
        iir_fixes = self._fix_ingredient_in_recipe(dry_run)

        if group_fixes + iir_fixes == 0:
            self.stdout.write(self.style.SUCCESS("No duplicates found."))
        else:
            verb = "Would fix" if dry_run else "Fixed"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{verb} {group_fixes} IngredientGroup row(s) and "
                    f"{iir_fixes} IngredientInRecipe row(s)."
                )
            )
            if dry_run:
                raise SystemExit(0)

    def _fix_ingredient_groups(self, dry_run: bool) -> int:
        fixes = 0
        recipe_ids = IngredientGroup.objects.values_list("recipe_id", flat=True).distinct()
        for recipe_id in recipe_ids:
            groups = list(
                IngredientGroup.objects.filter(recipe_id=recipe_id).order_by(
                    "index_in_sequence", "id"
                )
            )
            seen: set[int] = set()
            for group in groups:
                if group.index_in_sequence in seen:
                    new_index = max(seen) + 1
                    self.stdout.write(
                        f"IngredientGroup id={group.id} recipe_id={recipe_id}: "
                        f"index {group.index_in_sequence} → {new_index}"
                    )
                    if not dry_run:
                        group.index_in_sequence = new_index
                        group.save(update_fields=["index_in_sequence"])
                    seen.add(new_index)
                    fixes += 1
                else:
                    seen.add(group.index_in_sequence)
        return fixes

    def _fix_ingredient_in_recipe(self, dry_run: bool) -> int:
        fixes = 0
        group_ids = IngredientInRecipe.objects.values_list(
            "ingredient_group_id", flat=True
        ).distinct()
        for group_id in group_ids:
            rows = list(
                IngredientInRecipe.objects.filter(ingredient_group_id=group_id).order_by(
                    "index_in_sequence", "id"
                )
            )
            seen: set[int] = set()
            for row in rows:
                if row.index_in_sequence in seen:
                    new_index = max(seen) + 1
                    self.stdout.write(
                        f"IngredientInRecipe id={row.id} group_id={group_id}: "
                        f"index {row.index_in_sequence} → {new_index}"
                    )
                    if not dry_run:
                        row.index_in_sequence = new_index
                        row.save(update_fields=["index_in_sequence"])
                    seen.add(new_index)
                    fixes += 1
                else:
                    seen.add(row.index_in_sequence)
        return fixes
