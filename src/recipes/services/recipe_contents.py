"""Load a recipe's ingredient groups and rows in a fixed number of queries (#64).

Every template that walks `recipe.ingredient_groups` or `group.items`
reads each row's ingredient, substitute and unit. Without these prefetches each
group and each row costs queries of its own, so a re-render grows with the
recipe. Call these after any write the render has to show: a lookup already
prefetched on an instance is not fetched again.
"""

from django.db.models import Prefetch, QuerySet, prefetch_related_objects

from recipes.models import IngredientGroup, IngredientInRecipe, Recipe


def _rows() -> QuerySet:
    return IngredientInRecipe.objects.select_related("ingredient", "substitute", "unit")


def ingredients_prefetch() -> Prefetch:
    """A recipe's groups, each with its rows and what they display."""
    return Prefetch("ingredient_groups__items", queryset=_rows())


def with_ingredients(recipe: Recipe) -> Recipe:
    """`recipe`, its groups and their rows prefetched for rendering."""
    prefetch_related_objects([recipe], ingredients_prefetch())
    return recipe


def with_rows(group: IngredientGroup) -> IngredientGroup:
    """`group` with its rows prefetched for rendering."""
    prefetch_related_objects([group], Prefetch("items", queryset=_rows()))
    return group
