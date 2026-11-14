"""Export a user's recipes as a Nutrisho document, for a lossless round trip (#78).

The document is plain JSON (see `recipe_document.py` for the format). It holds
every column of every recipe the user owns, trashed ones included, with
ingredients, units, tags and cuisines by name rather than id, so it can be
imported on another server. Text is as typed, markup and all, and quantities are
decimal strings, so nothing is rounded on the way out.
"""

from datetime import datetime
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step
from recipes.services.name_resolution import cuisine_path_map
from recipes.services.recipe_contents import ingredients_prefetch
from recipes.services.recipe_document import FORMAT, VERSION


def export_recipes(*, owner: AbstractBaseUser) -> dict[str, Any]:
    """All of `owner`'s recipes, live and trashed, oldest first, in a fixed number of queries."""
    recipes = (
        Recipe.objects.filter(owner=owner)
        .prefetch_related("steps", "tags", ingredients_prefetch())
        .order_by("id")
    )
    paths = cuisine_path_map()
    used: dict[str, Ingredient] = {}
    exported = [_recipe(recipe, paths=paths, used=used) for recipe in recipes]
    return {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": timezone.now().isoformat(),
        "ingredients": [_ingredient(row) for _, row in sorted(used.items())],
        "recipes": exported,
    }


def _when(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _recipe(recipe: Recipe, *, paths: dict[int, str], used: dict[str, Ingredient]) -> dict:
    return {
        "recipe_name": recipe.recipe_name,
        "short_description": recipe.short_description,
        "servings": recipe.servings,
        "source_instance": recipe.source_instance,
        "cuisine": paths.get(recipe.cuisine_id, "") if recipe.cuisine_id else "",
        "tags": sorted((str(tag.tag) for tag in recipe.tags.all()), key=str.lower),  # ty: ignore[unresolved-attribute]  # reverse M2M
        "created_date": _when(recipe.created_date),  # ty: ignore[invalid-argument-type]  # no Django stubs
        "deleted_at": _when(recipe.deleted_at),  # ty: ignore[invalid-argument-type]  # no Django stubs
        "steps": [_step(step) for step in recipe.steps.all()],  # ty: ignore[unresolved-attribute]  # reverse FK
        "ingredient_groups": [
            _group(group, used=used)
            for group in recipe.ingredient_groups.all()  # ty: ignore[unresolved-attribute]  # reverse FK
        ],
    }


def _step(step: Step) -> dict:
    return {"step_title": step.step_title, "step_text": step.step_text}


def _group(group: IngredientGroup, *, used: dict[str, Ingredient]) -> dict:
    return {
        "group_name": group.group_name,
        "items": [_row(row, used=used) for row in group.items.all()],  # ty: ignore[unresolved-attribute]  # reverse FK
    }


def _row(row: IngredientInRecipe, *, used: dict[str, Ingredient]) -> dict:
    ingredient: Ingredient = row.ingredient  # ty: ignore[invalid-assignment]  # FK descriptor
    substitute: Ingredient | None = row.substitute  # ty: ignore[invalid-assignment]  # FK descriptor
    for each in (ingredient, substitute):
        if each is not None:
            used.setdefault(str(each.ingredient_name).lower(), each)
    return {
        "ingredient": ingredient.ingredient_name,
        "substitute": substitute.ingredient_name if substitute is not None else "",
        "quantity": str(row.quantity) if row.quantity is not None else None,
        "unit": row.unit.name if row.unit is not None else "",
        "legacy_unit": row.legacy_unit,
        "preparation": row.preparation,
        "note": row.note,
    }


def _ingredient(row: Ingredient) -> dict:
    return {
        "ingredient_name": row.ingredient_name,
        "plural_name": row.plural_name,
        "family": row.family,
        "dietary_constraint": row.dietary_constraint,
    }
