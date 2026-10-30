"""Resolve names typed into the recipe editor to `Ingredient` and `Cuisine` rows.

Both names are unique ignoring case, so `Onion` typed on a phone that
auto-capitalises is the stored `onion`, not a second row. Lookups are
case-insensitive and keep the stored spelling; a miss creates the row as typed.
Every editor path goes through here rather than calling `get_or_create` on the
raw name, which matched case-sensitively and then hit the unique index (#34).
"""

from recipes.models import Cuisine, Ingredient


def find_ingredient(name: str) -> Ingredient | None:
    """The ingredient called `name` ignoring case and surrounding space, if any."""
    return Ingredient.objects.filter(ingredient_name__iexact=name.strip()).first()


def resolve_ingredient(name: str) -> Ingredient:
    """The ingredient called `name` ignoring case, created as typed on a miss."""
    name = name.strip()
    ingredient, _ = Ingredient.objects.get_or_create(
        ingredient_name__iexact=name, defaults={"ingredient_name": name}
    )
    return ingredient


def find_cuisine(name: str) -> Cuisine | None:
    """The cuisine called `name` ignoring case and surrounding space, if any."""
    return Cuisine.objects.filter(cuisine__iexact=name.strip()).first()


def resolve_cuisine(name: str) -> Cuisine:
    """The cuisine called `name` ignoring case, created as typed on a miss."""
    name = name.strip()
    cuisine, _ = Cuisine.objects.get_or_create(cuisine__iexact=name, defaults={"cuisine": name})
    return cuisine
