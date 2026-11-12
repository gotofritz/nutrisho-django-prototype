"""Create a recipe and save its metadata: name, description, servings, source, cuisine, tags (#77).

An owner's recipe names are unique, so a save that would clash raises
`DuplicateRecipeNameError` and writes nothing, tags included. A save whose recipe
has gone raises `ObjectDoesNotExist` once its transaction has closed: nothing
has been written by then, so there is nothing to roll back.
"""

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction

from recipes.models import Recipe
from recipes.services.name_resolution import resolve_tag

_METADATA_FIELDS = ["recipe_name", "short_description", "servings", "source_instance", "cuisine"]


class DuplicateRecipeNameError(ValueError):
    """The owner already has a recipe with that name."""

    def __init__(self) -> None:
        """Carry the message the forms show."""
        super().__init__("You already have a recipe with that name.")


def set_tags(recipe: Recipe, *, names: list[str]) -> None:
    """Give the recipe exactly the named tags, resolved within its owner's vocabulary.

    An unknown name becomes a tag private to the owner. Call inside the write's
    transaction.
    """
    tags = [resolve_tag(name, owner=recipe.owner) for name in names]
    recipe.tag.set(tags)  # ty: ignore[unresolved-attribute]  # reverse M2M


def _lock(recipe: Recipe) -> bool:
    return bool(list(Recipe.objects.filter(pk=recipe.pk).select_for_update().values("pk")))


def create_recipe(*, owner: AbstractBaseUser, recipe: Recipe, tag_names: list[str]) -> Recipe:
    """Save `recipe`, its fields already set, as `owner`'s, with the named tags."""
    recipe.owner = owner  # ty: ignore[invalid-assignment]  # FK descriptor
    try:
        with transaction.atomic():
            recipe.save()
            set_tags(recipe, names=tag_names)
    except IntegrityError as exc:
        raise DuplicateRecipeNameError from exc
    return recipe


def save_metadata(*, recipe: Recipe, tag_names: list[str]) -> None:
    """Save `recipe`'s metadata fields, already set, and its tags."""
    try:
        with transaction.atomic():
            found = _lock(recipe)
            if found:
                recipe.save(update_fields=_METADATA_FIELDS)
                set_tags(recipe, names=tag_names)
    except IntegrityError as exc:
        raise DuplicateRecipeNameError from exc
    if not found:
        msg = "The recipe has been deleted."
        raise ObjectDoesNotExist(msg)


def save_field(*, recipe: Recipe, field_name: str) -> None:
    """Save one of `recipe`'s fields, already set, and nothing else."""
    try:
        with transaction.atomic():
            found = _lock(recipe)
            if found:
                recipe.save(update_fields=[field_name])
    except IntegrityError as exc:
        raise DuplicateRecipeNameError from exc
    if not found:
        msg = "The recipe has been deleted."
        raise ObjectDoesNotExist(msg)
