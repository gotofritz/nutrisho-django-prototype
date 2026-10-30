"""Tests for resolving typed ingredient and cuisine names to rows (#34)."""

import importlib

import pytest
from django.db import IntegrityError

from recipes.models import Cuisine, Ingredient, Recipe
from recipes.services.name_resolution import (
    find_cuisine,
    find_ingredient,
    resolve_cuisine,
    resolve_ingredient,
)


@pytest.mark.django_db
def test_resolve_ingredient_reuses_row_ignoring_case(make_ingredient):
    """`Onion` resolves to the stored `onion` and keeps its spelling."""
    onion = make_ingredient("onion")
    assert resolve_ingredient("Onion") == onion
    assert Ingredient.objects.count() == 1
    onion.refresh_from_db()
    assert onion.ingredient_name == "onion"


@pytest.mark.django_db
def test_resolve_ingredient_strips_whitespace(make_ingredient):
    """Surrounding whitespace is not part of the name."""
    onion = make_ingredient("onion")
    assert resolve_ingredient("  ONION ") == onion


@pytest.mark.django_db
def test_resolve_ingredient_creates_on_miss_as_typed():
    """A new name is created with the spelling the user typed."""
    ingredient = resolve_ingredient(" Shallot ")
    assert ingredient.ingredient_name == "Shallot"
    assert Ingredient.objects.count() == 1


@pytest.mark.django_db
def test_resolve_ingredient_does_not_match_substrings(make_ingredient):
    """`iexact` is an equality test: `onion` does not resolve to `red onion`."""
    make_ingredient("red onion")
    assert resolve_ingredient("onion").ingredient_name == "onion"
    assert Ingredient.objects.count() == 2


@pytest.mark.django_db
def test_resolve_ingredient_treats_like_wildcards_literally(make_ingredient):
    """`%` and `_` in a name are characters, not LIKE wildcards."""
    make_ingredient("salt")
    assert resolve_ingredient("s_lt").ingredient_name == "s_lt"
    assert resolve_ingredient("%").ingredient_name == "%"


@pytest.mark.django_db
def test_find_ingredient_ignores_case_and_never_creates(make_ingredient):
    """`find_ingredient` looks up only."""
    onion = make_ingredient("onion")
    assert find_ingredient(" ONION") == onion
    assert find_ingredient("leek") is None
    assert Ingredient.objects.count() == 1


@pytest.mark.django_db
def test_resolve_cuisine_reuses_row_ignoring_case():
    """`italian` resolves to the stored `Italian`."""
    italian = Cuisine.objects.create(cuisine="Italian")
    assert resolve_cuisine(" italian ") == italian
    assert Cuisine.objects.count() == 1


@pytest.mark.django_db
def test_resolve_cuisine_creates_on_miss_as_typed():
    """A new cuisine is created with the spelling the user typed."""
    assert resolve_cuisine("Peruvian ").cuisine == "Peruvian"


@pytest.mark.django_db
def test_find_cuisine_ignores_case_and_never_creates():
    """`find_cuisine` looks up only."""
    italian = Cuisine.objects.create(cuisine="Italian")
    assert find_cuisine("ITALIAN") == italian
    assert find_cuisine("Thai") is None
    assert Cuisine.objects.count() == 1


@pytest.mark.django_db
def test_cuisine_names_are_unique_ignoring_case():
    """The database refuses a second cuisine that differs only by case."""
    Cuisine.objects.create(cuisine="Italian")
    with pytest.raises(IntegrityError):
        Cuisine.objects.create(cuisine="italian")


@pytest.fixture
def without_cuisine_ci_constraint(db):
    """Drop the case-insensitive cuisine index so pre-#34 clashes can exist."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX cuisine_ci_unique")


def _merge():
    """The data step migration 0017 runs before adding its constraint."""
    from django.apps import apps

    module = importlib.import_module("recipes.migrations.0017_cuisine_cuisine_ci_unique")
    return lambda: module.merge_case_insensitive_duplicates(apps, None)


@pytest.mark.django_db
def test_migration_merges_cuisines_into_the_most_used_spelling(without_cuisine_ci_constraint, user):
    """Recipes move to the most-used spelling; the other rows go."""
    lower = Cuisine.objects.create(cuisine="italian")
    upper = Cuisine.objects.create(cuisine="Italian")
    Cuisine.objects.create(cuisine="Thai")
    Recipe.objects.create(recipe_name="A", owner=user, cuisine=lower)
    Recipe.objects.create(recipe_name="B", owner=user, cuisine=upper)
    Recipe.objects.create(recipe_name="C", owner=user, cuisine=upper)
    _merge()()
    assert set(Cuisine.objects.values_list("cuisine", flat=True)) == {"Italian", "Thai"}
    assert set(Recipe.objects.values_list("cuisine_id", flat=True)) == {upper.pk}


@pytest.mark.django_db
def test_migration_merge_breaks_ties_on_oldest_row(without_cuisine_ci_constraint, user):
    """With equal use, the row created first wins."""
    first = Cuisine.objects.create(cuisine="italian")
    second = Cuisine.objects.create(cuisine="ITALIAN")
    Recipe.objects.create(recipe_name="A", owner=user, cuisine=second)
    Recipe.objects.create(recipe_name="B", owner=user, cuisine=first)
    _merge()()
    assert list(Cuisine.objects.values_list("pk", flat=True)) == [first.pk]
    assert set(Recipe.objects.values_list("cuisine_id", flat=True)) == {first.pk}
