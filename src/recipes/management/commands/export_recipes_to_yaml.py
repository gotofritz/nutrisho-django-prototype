"""Export recipes from the database to YAML files matching the existing schema."""

from pathlib import Path

import yaml
from django.core.management.base import BaseCommand, CommandError

from recipes.models import Recipe
from recipes.utils.filename import safe_filename, sanitize_stored_filename

__all__ = ["safe_filename", "sanitize_stored_filename"]


# Fields persisted on Recipe/Step/IngredientInRecipe that the YAML schema does NOT cover.
# Export refuses recipes carrying values in these fields unless --force is given.
# Notes:
#   - Recipe.owner is checked against the importer's hardcoded "gotofritz" username;
#     any other owner is dropped on re-import.
#   - Recipe.created_date is excluded: it is auto_now_add, so every re-import regenerates
#     it. Treating it as lossy would flag every recipe and make export unusable.
_IMPORTER_OWNER_USERNAME = "gotofritz"


def lossy_fields(recipe: Recipe) -> list[str]:
    """Return descriptions of fields whose values are dropped on export → re-import."""
    reasons: list[str] = []
    owner = recipe.owner  # ty: ignore[possibly-missing-attribute]
    owner_username = owner.username if owner is not None else None  # ty: ignore[possibly-missing-attribute]
    if owner_username != _IMPORTER_OWNER_USERNAME:
        reasons.append(f"owner={owner_username!r} (importer assigns {_IMPORTER_OWNER_USERNAME!r})")
    if recipe.source_id is not None:  # ty: ignore[unresolved-attribute]
        reasons.append(f"source FK (id={recipe.source_id})")  # ty: ignore[unresolved-attribute]
    for step in recipe.step.all():  # ty: ignore[unresolved-attribute]
        if step.duration is not None:
            reasons.append(f"step #{step.index_in_sequence}.duration")
        if step.extra_info:
            reasons.append(f"step #{step.index_in_sequence}.extra_info")
    for group in recipe.ingredients_group.all():  # ty: ignore[unresolved-attribute]
        for iir in group.ingredient.all():
            if iir.substitute_id is not None:
                reasons.append(f"ingredient {iir.ingredient.ingredient_name!r}.substitute")
            if iir.note:
                reasons.append(f"ingredient {iir.ingredient.ingredient_name!r}.note")
    return reasons


def recipe_to_dict(recipe: Recipe) -> dict:
    """Serialise a Recipe instance to a dict matching the YAML schema."""
    steps = [step.step_text for step in recipe.step.all()]  # ty: ignore[unresolved-attribute]

    groups = []
    for group in recipe.ingredients_group.all():  # ty: ignore[unresolved-attribute]
        ingredients = []
        for iir in group.ingredient.all():
            ingredients.append(
                {
                    "name": iir.ingredient.ingredient_name,
                    "measurement": iir.unit,
                    "preparation": iir.preparation,
                    "quantity": str(iir.quantity) if iir.quantity is not None else None,
                }
            )
        groups.append(
            {
                "name": group.group_name,
                "ingredient": ingredients,
            }
        )

    tags = sorted(t.tag for t in recipe.tag.all())  # ty: ignore[unresolved-attribute]

    ingredients: dict = {"group": groups}
    if recipe.servings is not None:
        ingredients["serves"] = recipe.servings

    return {
        "title": recipe.recipe_name,
        "description": recipe.short_description,
        "cuisine": recipe.cuisine.cuisine if recipe.cuisine else None,  # ty: ignore[possibly-missing-attribute]
        "source": recipe.source_instance or "",
        "tags": tags,
        "directions": {"step": steps},
        "ingredients": ingredients,
    }


class Command(BaseCommand):
    """Export recipes from DB to YAML files.

    The YAML schema is a subset of the persisted model. Fields not in the schema
    (owner, source FK, Step.duration, Step.extra_info, IngredientInRecipe.substitute,
    IngredientInRecipe.note) would be dropped on re-import. Export refuses such
    recipes by default; use --force to acknowledge the loss and proceed.

    Usage:
      python manage.py export_recipes_to_yaml recipes_yaml/
      python manage.py export_recipes_to_yaml recipes_yaml/ --id 42
      python manage.py export_recipes_to_yaml recipes_yaml/ --missing-only
      python manage.py export_recipes_to_yaml recipes_yaml/ --force
    """

    help = "Export recipes from the database to YAML files"

    def add_arguments(self, parser):
        parser.add_argument("output_dir", type=str, help="Directory to write YAML files into")
        parser.add_argument(
            "--id", type=int, dest="id", default=None, help="Export only this recipe ID"
        )
        parser.add_argument(
            "--missing-only",
            action="store_true",
            dest="missing_only",
            default=False,
            help="Skip recipes that already have a YAML file in the output directory",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            dest="force",
            default=False,
            help="Export even when recipe data does not round-trip cleanly (warn on stderr)",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"])
        if output_dir.exists() and not output_dir.is_dir():
            raise CommandError(f"'{output_dir}' exists and is not a directory")
        output_dir.mkdir(parents=True, exist_ok=True)

        recipe_id = options["id"]
        qs = Recipe.objects.all()
        if recipe_id is not None:
            qs = qs.filter(pk=recipe_id)
            if not qs.exists():
                raise CommandError(f"No recipe found with id={recipe_id}")

        # Pre-scan existing files case-insensitively; used only for --missing-only skip logic.
        # Abort early if two existing files differ only in case — the casefold dict would silently
        # collapse them, leaving a stale duplicate on disk after export.
        existing_on_disk: dict[str, str] = {}
        for _f in output_dir.iterdir():
            if not _f.is_file() or _f.suffix.lower() not in {".yml", ".yaml"}:
                continue
            _key = _f.name.casefold()
            if _key in existing_on_disk:
                raise CommandError(
                    f"Ambiguous files in '{output_dir}': '{existing_on_disk[_key]}' and "
                    f"'{_f.name}' collide case-insensitively. Resolve before exporting."
                )
            existing_on_disk[_key] = _f.name

        # Separate recipes to write from those skipped by --missing-only
        to_write: list[tuple[Recipe, Path]] = []
        skipped = 0
        for recipe in qs:
            stored = str(recipe.yaml_filename)  # ty: ignore[unresolved-attribute]
            pk_fallback = f"recipe-{recipe.pk}"
            filename = (
                sanitize_stored_filename(stored, fallback=pk_fallback)
                if stored
                else safe_filename(str(recipe.recipe_name), fallback=pk_fallback)
            )
            key = filename.casefold()
            if options["missing_only"] and key in existing_on_disk:
                skipped += 1
            else:
                # In normal mode: if a case-only variant already exists on disk, write to that
                # path so we overwrite it rather than creating a second file alongside it.
                actual_filename = existing_on_disk.get(key, filename)
                out_path = output_dir / actual_filename
                to_write.append((recipe, out_path))

        # Detect collisions (case-insensitive) within the current export batch only
        # Existing files on disk are NOT collisions in normal mode — they are overwritten
        seen: dict[str, str] = {}  # casefold(filename) -> recipe name
        for recipe, out_path in to_write:
            filename = out_path.name
            key = filename.casefold()
            if key in seen:
                raise CommandError(
                    f"Filename collision: '{recipe.recipe_name}' and '{seen[key]}' "
                    f"both map to '{filename}' (case-insensitive). "
                    f"Rename one recipe before exporting."
                )
            seen[key] = str(recipe.recipe_name)

        # Preflight: ensure no target path is a non-file (e.g. a directory)
        for _recipe, out_path in to_write:
            if out_path.exists() and not out_path.is_file():
                raise CommandError(
                    f"Cannot write '{out_path}': path exists and is not a regular file"
                )

        # Preflight: refuse recipes carrying data the YAML schema cannot represent.
        # --force converts the refusal into a stderr warning per recipe.
        lossy_report: list[tuple[Recipe, list[str]]] = []
        for recipe, _ in to_write:
            reasons = lossy_fields(recipe)
            if reasons:
                lossy_report.append((recipe, reasons))

        if lossy_report:
            if not options["force"]:
                lines = [
                    "Refusing to export lossy recipes (use --force to override):",
                ]
                for r, reasons in lossy_report:
                    lines.append(f"  '{r.recipe_name}': {', '.join(reasons)}")
                raise CommandError("\n".join(lines))
            for r, reasons in lossy_report:
                self.stderr.write(
                    self.style.WARNING(
                        f"Lossy export of '{r.recipe_name}': dropping {', '.join(reasons)}"
                    )
                )

        exported = 0
        for recipe, out_path in to_write:
            data = recipe_to_dict(recipe)
            with out_path.open("w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=True, default_flow_style=False)
            # Backfill stable filename for rows that never had one; future exports
            # (including --missing-only) always match on the stored value, not the
            # current recipe_name, so renames don't cause stale duplicate files.
            if not recipe.yaml_filename:  # ty: ignore[unresolved-attribute]
                recipe.yaml_filename = out_path.name  # ty: ignore[unresolved-attribute]
                recipe.save(update_fields=["yaml_filename"])
            exported += 1

        self.stdout.write(self.style.SUCCESS(f"Exported {exported} recipe(s), skipped {skipped}"))
