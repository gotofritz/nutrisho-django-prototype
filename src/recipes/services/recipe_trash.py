"""Move recipes to the trash, bring them back, or delete them for good (#75).

A trashed recipe keeps its row and every child row; only `deleted_at` is set,
so restoring it is one write. The name rule covers live recipes only, so a
recipe restored after its name was reused comes back as "<name> Restored".
"""

from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from recipes.models import Recipe

_NAME_MAX = 200  # Recipe.recipe_name max_length


def trash_recipe(recipe: Recipe) -> None:
    """Move `recipe` to the trash."""
    with transaction.atomic():
        recipe.deleted_at = timezone.now()
        recipe.save(update_fields=["deleted_at"])


def restore_recipe(recipe: Recipe) -> Recipe:
    """Take `recipe` out of the trash, renaming it if a live recipe has its name."""
    base = str(recipe.recipe_name)
    n = 0
    with transaction.atomic():
        while True:
            recipe.recipe_name = _restored_name(base, n)  # ty: ignore[invalid-assignment]  # no Django stubs
            recipe.deleted_at = None  # ty: ignore[invalid-assignment]  # no Django stubs
            try:
                with transaction.atomic():
                    recipe.save(update_fields=["deleted_at", "recipe_name"])
                    return recipe
            except IntegrityError:
                n += 1


def _restored_name(base: str, n: int) -> str:
    """'Base', then 'Base Restored', 'Base Restored 2', …"""
    if n == 0:
        return base
    suffix = " Restored" if n == 1 else f" Restored {n}"
    return f"{base[: _NAME_MAX - len(suffix)]}{suffix}"


def purge_recipe(recipe: Recipe) -> None:
    """Delete a trashed `recipe` and everything in it for good."""
    with transaction.atomic():
        recipe.delete()


def trashed_recipes(*, owner: AbstractBaseUser) -> QuerySet:
    """`owner`'s trashed recipes, most recently deleted first."""
    return Recipe.objects.trashed().filter(owner=owner).order_by("-deleted_at", "-id")
