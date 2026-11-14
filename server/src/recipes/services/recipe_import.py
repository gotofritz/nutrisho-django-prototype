"""Write imported recipes for a user (#78).

`parse_document` reads a file or request body into drafts; `import_recipes`
writes them as new recipes of `owner`, never touching one they already have.
Names go through `name_resolution` as typed names do: ingredients and tags the
owner cannot see become private to them, while a cuisine or unit the server
does not know is never created. An unknown unit stays as written in
`legacy_unit`, and an unknown cuisine is left blank; both come back as warnings.

A recipe whose name the owner already uses is imported as "<name> Imported"
(" Imported 2", …), so importing never loses either recipe. Each recipe is
written in its own transaction, so a large import does not hold the write lock
for its whole length.
"""

from dataclasses import dataclass, field

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from recipes.models import (
    Cuisine,
    Ingredient,
    IngredientGroup,
    IngredientInRecipe,
    Recipe,
    Step,
    Unit,
)
from recipes.services.name_resolution import find_cuisine, find_unit, resolve_ingredient
from recipes.services.recipe_document import ImportBatch, IngredientDraft, RecipeDraft, RowDraft
from recipes.services.recipe_metadata import set_tags
from recipes.utils.plain_text import plain_text
from recipes.utils.sequencing import number_in_order

_NAME_MAX = 200  # Recipe.recipe_name max_length


@dataclass(frozen=True)
class ImportedRecipe:
    """A recipe an import wrote, and the name it asked for when that was taken."""

    recipe: Recipe
    requested_name: str = ""

    @property
    def renamed(self) -> bool:
        """Whether the recipe took another name because its own was taken."""
        return bool(self.requested_name)


@dataclass
class ImportResult:
    """What an import wrote, and what it could not carry over."""

    recipes: list[ImportedRecipe] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def import_recipes(*, owner: AbstractBaseUser, batch: ImportBatch) -> ImportResult:
    """Write every recipe in `batch` as `owner`'s, in order."""
    writer = _Writer(owner=owner, ingredients=batch.ingredients)
    for draft in batch.recipes:
        with transaction.atomic():
            writer.result.recipes.append(writer.write(draft))
    return writer.result


class _Writer:
    """Writes drafts, remembering names it has resolved across the import."""

    def __init__(self, *, owner: AbstractBaseUser, ingredients: dict[str, IngredientDraft]) -> None:
        self.result = ImportResult()
        self._owner = owner
        self._known = ingredients
        self._ingredients: dict[str, Ingredient] = {}
        self._units: dict[str, Unit | None] = {}
        self._cuisines: dict[str, Cuisine | None] = {}

    def write(self, draft: RecipeDraft) -> ImportedRecipe:
        label = plain_text(draft.recipe_name)
        recipe = Recipe(
            recipe_name=draft.recipe_name,
            short_description=draft.short_description,
            servings=draft.servings,
            source_instance=draft.source_instance,
            cuisine=self._cuisine(draft.cuisine, label=label),
            owner=self._owner,
            deleted_at=draft.deleted_at,
        )
        imported = _save_with_free_name(recipe)
        if draft.created_date is not None:
            # `auto_now_add` ignores a value given on create.
            Recipe.objects.filter(pk=recipe.pk).update(created_date=draft.created_date)
            recipe.created_date = draft.created_date  # ty: ignore[invalid-assignment]  # no Django stubs
        set_tags(recipe, names=list(draft.tags))
        steps = [
            Step(recipe=recipe, step_title=step.step_title, step_text=step.step_text)
            for step in draft.steps
        ]
        number_in_order(steps)
        Step.objects.bulk_create(steps)
        groups = [
            IngredientGroup(recipe=recipe, group_name=group.group_name)
            for group in draft.ingredient_groups
        ]
        number_in_order(groups)
        IngredientGroup.objects.bulk_create(groups)
        rows = []
        for group, group_draft in zip(groups, draft.ingredient_groups, strict=True):
            items = [self._row(item, group=group, label=label) for item in group_draft.items]
            number_in_order(items)
            rows.extend(items)
        IngredientInRecipe.objects.bulk_create(rows)
        return imported

    def _row(self, draft: RowDraft, *, group: IngredientGroup, label: str) -> IngredientInRecipe:
        unit = self._unit(draft.unit)
        legacy_unit = draft.legacy_unit
        if draft.unit.strip() and unit is None:
            legacy_unit = legacy_unit or draft.unit.strip()
            self.result.warnings.append(
                f"“{label}”: “{draft.unit.strip()}” is not a unit here, so it is kept as written."
            )
        return IngredientInRecipe(
            ingredient_group=group,
            ingredient=self._ingredient(draft.ingredient),
            substitute=self._ingredient(draft.substitute) if draft.substitute.strip() else None,
            quantity=draft.quantity,
            unit=unit,
            legacy_unit=legacy_unit,
            preparation=draft.preparation,
            note=draft.note,
        )

    def _ingredient(self, name: str) -> Ingredient:
        key = name.strip().lower()
        if key not in self._ingredients:
            known = self._known.get(key)
            defaults = (
                {
                    "plural_name": known.plural_name,
                    "family": known.family,
                    "dietary_constraint": known.dietary_constraint,
                }
                if known is not None
                else None
            )
            self._ingredients[key] = resolve_ingredient(name, owner=self._owner, defaults=defaults)
        return self._ingredients[key]

    def _unit(self, text: str) -> Unit | None:
        key = text.strip().lower()
        if not key:
            return None
        if key not in self._units:
            self._units[key] = find_unit(text)
        return self._units[key]

    def _cuisine(self, path: str, *, label: str) -> Cuisine | None:
        key = path.strip().lower()
        if not key:
            return None
        if key not in self._cuisines:
            self._cuisines[key] = find_cuisine(path)
        cuisine = self._cuisines[key]
        if cuisine is None:
            self.result.warnings.append(
                f"“{label}”: there is no cuisine “{path.strip()}” here, so it has none."
            )
        return cuisine


def _save_with_free_name(recipe: Recipe) -> ImportedRecipe:
    """Save `recipe`, adding " Imported" (" Imported 2", …) while a live recipe has its name.

    Only live recipes hold a name (#75), so a recipe imported into the trash
    keeps its own. The check and the save share the caller's transaction, whose
    IMMEDIATE lock keeps another write from taking the name in between.
    """
    base = str(recipe.recipe_name)
    n = 0
    if recipe.deleted_at is None:
        taken = Recipe.objects.live().filter(owner=recipe.owner)
        while taken.filter(plain_name=plain_text(_imported_name(base, n))).exists():
            n += 1
    recipe.recipe_name = _imported_name(base, n)  # ty: ignore[invalid-assignment]  # no Django stubs
    recipe.save()
    return ImportedRecipe(recipe=recipe, requested_name=base if n else "")


def _imported_name(base: str, n: int) -> str:
    """'Base', then 'Base Imported', 'Base Imported 2', …"""
    if n == 0:
        return base
    suffix = " Imported" if n == 1 else f" Imported {n}"
    return f"{base[: _NAME_MAX - len(suffix)]}{suffix}"
