"""Limits on the JSON API the recipe clipper uses (#149, plan 012 M10).

Rate limits count requests in Django's cache, in windows of a minute from the
first request in each: per API key, and per client address for failed
sign-ins. The cache is the default local-memory one, so the counts are per
process and start again on a restart; they are about load and noise, not
guessing, as keys have 256 bits. `new_name_count` says how many rows a save
would make the user, so one request cannot flood their suggestions.
"""

import math
import time

from django.contrib.auth.models import AbstractBaseUser
from django.core.cache import cache

from recipes.services.name_resolution import find_cuisine, find_ingredient, find_tag, find_unit
from recipes.services.recipe_document import ImportBatch
from recipes.utils.unit_words import not_a_unit

WINDOW_SECONDS = 60


def _now() -> float:
    return time.time()


def _key(scope: str, ident: str) -> str:
    return f"api-rate:{scope}:{ident}"


def wait_for(scope: str, ident: str, *, limit: int) -> int | None:
    """Seconds to wait before `ident` may send again, once it has sent `limit` this window; else None."""
    start, count = cache.get(_key(scope, ident), (0.0, 0))
    now = _now()
    if now - start >= WINDOW_SECONDS or count < limit:
        return None
    return max(1, math.ceil(start + WINDOW_SECONDS - now))


def note(scope: str, ident: str) -> None:
    """Count one request from `ident` in its window, starting a new window when the last has passed."""
    key = _key(scope, ident)
    start, count = cache.get(key, (0.0, 0))
    now = _now()
    if now - start >= WINDOW_SECONDS:
        start, count = now, 0
    cache.set(key, (start, count + 1), timeout=WINDOW_SECONDS)


def new_name_count(batch: ImportBatch, *, owner: AbstractBaseUser) -> int:
    """How many names the import would make `owner`: ingredients, units, tags and cuisines they lack.

    Each name counts once, ignoring case; a name they have by any spelling,
    and a size word in the unit field (which never becomes a unit), count
    for nothing.
    """
    ingredients: set[str] = set()
    units: set[str] = set()
    tags: set[str] = set()
    cuisines: set[str] = set()
    for recipe in batch.recipes:
        tags.update(tag.strip().lower() for tag in recipe.tags if tag.strip())
        if recipe.cuisine.strip():
            cuisines.add(recipe.cuisine.strip().lower())
        for group in recipe.ingredient_groups:
            for row in group.items:
                ingredients.update(
                    name.strip().lower()
                    for name in (row.ingredient, row.substitute)
                    if name.strip()
                )
                if row.unit.strip() and not_a_unit(row.unit) is None:
                    units.add(row.unit.strip().lower())
    return (
        sum(find_ingredient(name, owner=owner) is None for name in ingredients)
        + sum(find_unit(name, owner=owner) is None for name in units)
        + sum(find_tag(name, owner=owner) is None for name in tags)
        + sum(find_cuisine(name, owner=owner) is None for name in cuisines)
    )
