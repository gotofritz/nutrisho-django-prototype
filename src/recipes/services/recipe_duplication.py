"""Duplicate a recipe with its steps, ingredient groups, ingredients and tags.

Rows are copied generically from `_meta.concrete_fields`, so a column added to
any of these models is carried over without touching this module (#35). Foreign
keys are copied by id, and each level is written with one `bulk_create`, so the
number of queries does not grow with the size of the recipe.
"""

from django.db import IntegrityError, transaction
from django.db.models import Model

from recipes.models import IngredientGroup, IngredientInRecipe, Recipe, Step

_NAME_MAX = 200  # Recipe.recipe_name max_length


def duplicate_recipe(original: Recipe) -> Recipe:
    """Copy `original` under a free "<name> Copy[ N]" name and return the copy."""
    with transaction.atomic():
        new = _create_with_free_name(original)
        # IntegrityErrors from here on propagate; only the name is retried.
        Step.objects.bulk_create(
            _clone(step, recipe_id=new.pk) for step in Step.objects.filter(recipe=original)
        )
        groups = list(IngredientGroup.objects.filter(recipe=original))
        new_groups = IngredientGroup.objects.bulk_create(
            _clone(group, recipe_id=new.pk) for group in groups
        )
        new_group_ids = {old.pk: copied.pk for old, copied in zip(groups, new_groups, strict=True)}
        IngredientInRecipe.objects.bulk_create(
            _clone(iir, ingredient_group_id=new_group_ids[iir.ingredient_group_id])
            for iir in IngredientInRecipe.objects.filter(ingredient_group__recipe=original)
        )
        new.tag.add(*original.tag.all())  # ty: ignore[unresolved-attribute]  # reverse M2M
    return new


def _create_with_free_name(original: Recipe) -> Recipe:
    """Save a copy of `original`, bumping the name suffix on owner/name clashes."""
    n: int | None = None
    while True:
        try:
            with transaction.atomic():
                new = _clone(original, recipe_name=_copy_name(str(original.recipe_name), n))
                new.save()
                return new
        except IntegrityError:
            n = 2 if n is None else n + 1


def _copy_name(base: str, n: int | None = None) -> str:
    """Build a copy name: 'Base Copy', 'Base Copy 2', 'Base Copy 3', …"""
    suffix = f" Copy {n}" if n is not None else " Copy"
    return f"{base[: _NAME_MAX - len(suffix)]}{suffix}"


def _clone[M: Model](row: M, **overrides: object) -> M:
    """An unsaved copy of `row` with every concrete column but the pk.

    `overrides` are keyed by attname, e.g. `recipe_id`, so foreign keys are set
    by id without loading the related row.
    """
    values = {
        field.attname: getattr(row, field.attname)
        for field in row._meta.concrete_fields  # ty: ignore[unresolved-attribute]  # no Django stubs
        if not field.primary_key
    }
    return type(row)(**values | overrides)
