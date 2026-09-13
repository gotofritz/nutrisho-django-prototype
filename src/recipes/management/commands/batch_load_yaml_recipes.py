import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import DecimalValidator
from django.db import transaction

from recipes.models.cuisine import Cuisine
from recipes.models.ingredient import Ingredient
from recipes.models.ingredient_group import IngredientGroup
from recipes.models.ingredient_in_recipe import IngredientInRecipe
from recipes.models.recipe import Recipe
from recipes.models.step import Step
from recipes.models.tag import Tag
from recipes.utils.filename import safe_filename, sanitize_stored_filename

_UNICODE_FRACTIONS = {
    "½": "1/2",
    "⅓": "1/3",
    "⅔": "2/3",
    "¼": "1/4",
    "¾": "3/4",
    "⅕": "1/5",
    "⅖": "2/5",
    "⅗": "3/5",
    "⅘": "4/5",
    "⅙": "1/6",
    "⅚": "5/6",
    "⅛": "1/8",
    "⅜": "3/8",
    "⅝": "5/8",
    "⅞": "7/8",
}

_MIXED_UNICODE_RE = re.compile(
    r"(\d*)\s*(" + "|".join(re.escape(k) for k in _UNICODE_FRACTIONS) + ")"
)


def _normalize_quantity(raw: str) -> str:
    """Convert Unicode vulgar fractions and mixed numbers to plain decimal strings.

    E.g. '1½' → '1.5', '½' → '0.5', '¾' → '0.75'.
    """

    def _replace_unicode_frac(m: re.Match) -> str:
        whole = m.group(1) or "0"
        num_str, den_str = _UNICODE_FRACTIONS[m.group(2)].split("/")
        return str(Decimal(whole) + Decimal(num_str) / Decimal(den_str))

    s = _MIXED_UNICODE_RE.sub(_replace_unicode_frac, str(raw).strip())

    # "1 1/2" style mixed number
    mixed = re.fullmatch(r"(\d+)\s+(\d+)/(\d+)", s)
    if mixed:
        whole, num, den = int(mixed.group(1)), int(mixed.group(2)), int(mixed.group(3))
        if den == 0:
            raise InvalidOperation(f"zero denominator in fraction: {s!r}")
        return str(Decimal(whole) + Decimal(num) / Decimal(den))

    # "3/4" plain fraction
    frac = re.fullmatch(r"(\d+)/(\d+)", s)
    if frac:
        den = int(frac.group(2))
        if den == 0:
            raise InvalidOperation(f"zero denominator in fraction: {s!r}")
        return str(Decimal(int(frac.group(1))) / Decimal(den))

    return s


class Command(BaseCommand):
    help = "Adds a single recipe or a directory. Source must be yml"

    @classmethod
    def clean(cls, s):
        if s is None:
            return None
        tmp = re.sub(r"\n", " ", s)
        tmp = re.sub(r" {2,}", " ", tmp)
        return tmp.strip()

    @classmethod
    def _validate_payload(cls, recipe_dict: dict, source_path: Path) -> None:
        """Validate structure and normalize quantity fields in-place to Decimal/None.

        Mutates ingredient dicts so the write path reads the exact Decimal that was
        validated. Without this, the create() call would receive raw YAML values
        (floats for unquoted numerics) and Django's DecimalField would re-convert
        them through its own context, potentially diverging from the validated value.
        """
        groups = recipe_dict["ingredients"].get("group", [])
        if not isinstance(groups, list):
            groups = [groups]
        for group_dict in groups:
            ingredients = group_dict.get("ingredient", [])
            if not isinstance(ingredients, list):
                ingredients = [ingredients]
            for ingredient_raw in ingredients:
                qty = ingredient_raw.get("quantity")
                if qty is None or qty == "":
                    ingredient_raw["quantity"] = None
                    continue
                name = ingredient_raw.get("name", "?")
                try:
                    d = Decimal(_normalize_quantity(qty))
                except InvalidOperation as exc:
                    raise CommandError(
                        f"{source_path}: invalid quantity {qty!r} for ingredient '{name}'"
                    ) from exc
                try:
                    DecimalValidator(max_digits=7, decimal_places=2)(d)
                except DjangoValidationError as exc:
                    raise CommandError(
                        f"{source_path}: quantity {qty!r} for ingredient '{name}' "
                        f"exceeds field limits (max_digits=7, decimal_places=2): {exc.message}"
                    ) from exc
                ingredient_raw["quantity"] = d

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", type=str, help="Path to recipe")
        parser.add_argument(
            "--user",
            required=True,
            help="Username of the recipe owner (must already exist in the database)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Report changes without writing to DB",
        )

    @classmethod
    def _parse_serves(cls, serves_raw, source_path: Path) -> int:
        if serves_raw is None:
            raise CommandError(f"{source_path}: missing required 'serves' value")
        if isinstance(serves_raw, bool):
            raise CommandError(
                f"{source_path}: invalid serves value {serves_raw!r} (bool not allowed)"
            )
        if isinstance(serves_raw, float):
            raise CommandError(
                f"{source_path}: invalid serves value {serves_raw!r} (must be a whole number)"
            )
        try:
            serves = int(serves_raw)
        except (ValueError, TypeError) as exc:
            raise CommandError(f"{source_path}: invalid serves value {serves_raw!r}") from exc
        if serves <= 0:
            raise CommandError(f"{source_path}: serves must be > 0, got {serves}")
        if serves > 32767:
            raise CommandError(
                f"{source_path}: serves value {serves} exceeds PositiveSmallIntegerField max (32767)"
            )
        return serves

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        username = options["user"]
        try:
            owner: User = User.objects.get(username=username)
        except ObjectDoesNotExist:
            raise CommandError(f"User '{username}' not found in the database.")

        # Collect files
        files_to_load: list[Path] = []
        for passed_path in [Path(x) for x in options["paths"]]:
            if passed_path.is_dir():
                files_to_load += [
                    x
                    for x in passed_path.iterdir()
                    if x.is_file() and x.suffix.lower() in {".yml", ".yaml"}
                ]
            else:
                files_to_load.append(passed_path)

        # Phase 1: parse + validate all files before any DB writes
        payloads: list[tuple[Path, dict, int, str, str]] = []
        seen_names: dict[str, Path] = {}
        seen_filenames: dict[str, Path] = {}  # casefold(yaml_filename) -> source_path
        for source_path in files_to_load:
            with open(source_path, "r", encoding="utf-8") as stream:
                recipe_dict = yaml.safe_load(stream)
            self.stdout.write(self.style.NOTICE(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"))
            self.stdout.write(self.style.NOTICE(str(source_path)))
            self.stdout.write(self.style.NOTICE(json.dumps(recipe_dict, indent=2)))

            serves = Command._parse_serves(recipe_dict["ingredients"].get("serves"), source_path)
            Command._validate_payload(recipe_dict, source_path)

            recipe_name = Command.clean(recipe_dict["title"])
            if recipe_name in seen_names:
                raise CommandError(
                    f"Duplicate title '{recipe_name}' in {source_path} and {seen_names[recipe_name]}"
                )
            seen_names[recipe_name] = source_path

            yaml_filename = sanitize_stored_filename(source_path.name)
            fn_key = yaml_filename.casefold()
            if fn_key in seen_filenames:
                raise CommandError(
                    f"Filename collision: '{yaml_filename}' from {source_path} "
                    f"matches '{seen_filenames[fn_key]}' (case-insensitive)"
                )
            seen_filenames[fn_key] = source_path

            payloads.append((source_path, recipe_dict, serves, recipe_name, yaml_filename))

        # Phase 2: check DB conflicts for the whole batch at once
        existing = set(
            Recipe.objects.filter(owner=owner, recipe_name__in=seen_names).values_list(
                "recipe_name", flat=True
            )
        )
        if existing:
            conflicts = ", ".join(f"'{n}'" for n in sorted(existing))
            raise CommandError(f"Recipes already exist in DB for this owner: {conflicts}")

        existing_filenames: set[str] = set()
        for row in Recipe.objects.filter(owner=owner).values("pk", "yaml_filename", "recipe_name"):
            stored = row["yaml_filename"] or ""
            pk_fallback = f"recipe-{row['pk']}"
            if stored:
                effective = sanitize_stored_filename(stored, fallback=pk_fallback)
            else:
                effective = safe_filename(str(row["recipe_name"] or ""), fallback=pk_fallback)
            existing_filenames.add(effective.casefold())
        batch_fn_conflicts = seen_filenames.keys() & existing_filenames
        if batch_fn_conflicts:
            conflicts = ", ".join(f"'{k}'" for k in sorted(batch_fn_conflicts))
            raise CommandError(f"Filename collision with existing recipe(s) in DB: {conflicts}")

        if dry_run:
            for _path, _rd, serves, recipe_name, _fn in payloads:
                self.stdout.write(
                    self.style.WARNING(f"[dry-run] Would insert: {recipe_name} (serves={serves})")
                )
            self.stdout.write(self.style.SUCCESS("Successfully created plans"))
            return

        # Phase 3: write — single transaction so partial failures roll back the whole batch
        with transaction.atomic():
            for source_path, recipe_dict, serves, recipe_name, yaml_filename in payloads:
                if recipe_dict["cuisine"]:
                    cuisine, _ = Cuisine.objects.get_or_create(cuisine=recipe_dict["cuisine"])
                else:
                    cuisine = None

                recipe = Recipe.objects.create(
                    owner=owner,
                    recipe_name=recipe_name,
                    short_description=Command.clean(recipe_dict["description"]) or "",
                    source_instance=recipe_dict["source"] or "",
                    cuisine=cuisine,
                    servings=serves,
                    yaml_filename=yaml_filename,
                )

                steps = recipe_dict["directions"]["step"]
                if not isinstance(steps, list):
                    steps = [steps]
                for i, step_raw in enumerate(steps):
                    Step.objects.create(
                        recipe=recipe,
                        index_in_sequence=i + 1,
                        step_text=Command.clean(step_raw),
                    )

                if not isinstance(recipe_dict["ingredients"]["group"], list):
                    recipe_dict["ingredients"]["group"] = [recipe_dict["ingredients"]["group"]]
                for i, group_dict in enumerate(recipe_dict["ingredients"]["group"]):
                    group = IngredientGroup.objects.create(
                        recipe=recipe,
                        index_in_sequence=i + 1,
                        group_name=Command.clean(group_dict.get("name")) or "",
                    )
                    if not isinstance(group_dict["ingredient"], list):
                        group_dict["ingredient"] = [group_dict["ingredient"]]
                    for j, ingredient_raw in enumerate(group_dict["ingredient"]):
                        ingredient_name = Command.clean(ingredient_raw.get("name"))
                        ingredient, _ = Ingredient.objects.get_or_create(
                            ingredient_name=ingredient_name,
                        )
                        # quantity was normalized to Decimal-or-None by _validate_payload
                        IngredientInRecipe.objects.create(
                            ingredient=ingredient,
                            ingredient_group=group,
                            index_in_sequence=j + 1,
                            unit=ingredient_raw.get("measurement") or "",
                            preparation=ingredient_raw.get("preparation") or "",
                            quantity=ingredient_raw.get("quantity"),
                            note=ingredient_raw.get("note") or "",
                        )

                tags_raw = recipe_dict["tags"]
                if not isinstance(tags_raw, list):
                    tags_raw = [tags_raw]
                for tag_raw in tags_raw:
                    tag, _ = Tag.objects.get_or_create(tag=tag_raw.strip())
                    tag.recipe.add(recipe)

        self.stdout.write(self.style.SUCCESS("Successfully created plans"))
