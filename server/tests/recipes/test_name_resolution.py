"""Tests for resolving typed ingredient and cuisine names to rows (#34)."""

import importlib

import pytest
from django.db import IntegrityError

from recipes.models import Cuisine, Ingredient, Recipe
from recipes.services.name_resolution import (
    find_cuisine,
    find_ingredient,
    resolve_ingredient,
)


@pytest.mark.django_db
def test_resolve_ingredient_reuses_row_ignoring_case(make_ingredient, user):
    """`Onion` resolves to the stored `onion` and keeps its spelling."""
    onion = make_ingredient("onion")
    assert resolve_ingredient("Onion", owner=user) == onion
    assert Ingredient.objects.count() == 1
    onion.refresh_from_db()
    assert onion.ingredient_name == "onion"


@pytest.mark.django_db
def test_resolve_ingredient_strips_whitespace(make_ingredient, user):
    """Surrounding whitespace is not part of the name."""
    onion = make_ingredient("onion")
    assert resolve_ingredient("  ONION ", owner=user) == onion


@pytest.mark.django_db
def test_resolve_ingredient_creates_on_miss_as_typed(user):
    """A new name is created with the spelling the user typed."""
    ingredient = resolve_ingredient(" Shallot ", owner=user)
    assert ingredient.ingredient_name == "Shallot"
    assert Ingredient.objects.count() == 1


@pytest.mark.django_db
def test_resolve_ingredient_does_not_match_substrings(make_ingredient, user):
    """`iexact` is an equality test: `onion` does not resolve to `red onion`."""
    make_ingredient("red onion")
    assert resolve_ingredient("onion", owner=user).ingredient_name == "onion"
    assert Ingredient.objects.count() == 2


@pytest.mark.django_db
def test_resolve_ingredient_treats_like_wildcards_literally(make_ingredient, user):
    """`%` and `_` in a name are characters, not LIKE wildcards."""
    make_ingredient("salt")
    assert resolve_ingredient("s_lt", owner=user).ingredient_name == "s_lt"
    assert resolve_ingredient("%", owner=user).ingredient_name == "%"


@pytest.mark.django_db
def test_find_ingredient_ignores_case_and_never_creates(make_ingredient, user):
    """`find_ingredient` looks up only."""
    onion = make_ingredient("onion")
    assert find_ingredient(" ONION", owner=user) == onion
    assert find_ingredient("leek", owner=user) is None
    assert Ingredient.objects.count() == 1


@pytest.mark.django_db
def test_find_cuisine_ignores_case_and_never_creates():
    """`find_cuisine` looks up only; the editor never creates a cuisine (plan 011)."""
    before = Cuisine.objects.count()
    assert find_cuisine("MED.ITALY") == Cuisine.objects.get(cuisine="italy")
    assert find_cuisine("Klingon") is None
    assert Cuisine.objects.count() == before


@pytest.mark.django_db
def test_cuisine_names_are_unique_ignoring_case():
    """The database refuses a second cuisine that differs only by case."""
    Cuisine.objects.create(cuisine="Italian")
    with pytest.raises(IntegrityError):
        Cuisine.objects.create(cuisine="italian")


@pytest.fixture
def without_cuisine_ci_constraint(db):
    """Recreate the pre-#34 state: a flat table whose names may clash by case.

    Migration 0021 seeds the cuisine tree, whose repeated leaf names (`north`)
    would look like clashes to 0017's merge, so the tree goes first, leaves up.
    """
    from django.db import connection

    Cuisine.objects.filter(parent__parent__isnull=False).delete()
    Cuisine.objects.filter(parent__isnull=False).delete()
    Cuisine.objects.all().delete()
    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX cuisine_ci_unique")
        cursor.execute("DROP INDEX cuisine_ci_unique_per_parent")


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


@pytest.mark.django_db
def test_resolve_ingredient_maps_a_rule_plural_to_its_singular(make_ingredient, user):
    """`2 onions` is the stored `onion`, not a new `onions` row (#66)."""
    onion = make_ingredient("onion")
    assert resolve_ingredient("Onions", owner=user) == onion
    assert Ingredient.objects.count() == 1


@pytest.mark.django_db
def test_resolve_ingredient_maps_an_override_plural_to_its_singular(make_ingredient, user):
    """A `plural_name` override is matched too, ignoring case."""
    chili = make_ingredient("chili", plural_name="chilis")
    assert resolve_ingredient("CHILIS", owner=user) == chili
    assert Ingredient.objects.count() == 1


@pytest.mark.django_db
def test_resolve_ingredient_inflects_the_last_word_of_a_plural(make_ingredient, user):
    """`spring onions` is `spring onion`, as the plural rule spells it."""
    spring_onion = make_ingredient("spring onion")
    assert resolve_ingredient("spring onions", owner=user) == spring_onion


@pytest.mark.django_db
def test_resolve_ingredient_prefers_an_exact_name_over_a_plural(make_ingredient, user):
    """A stored `onions` row (legacy data) still wins over `onion`'s plural."""
    make_ingredient("onion")
    onions = make_ingredient("onions")
    assert resolve_ingredient("onions", owner=user) == onions


@pytest.mark.django_db
def test_resolve_ingredient_prefers_a_global_plural_match(make_ingredient, user):
    """The global row wins a plural match, as it wins a name match (plan 011)."""
    onion = make_ingredient("onion")
    Ingredient.objects.create(ingredient_name="Onion", owner=user)
    assert resolve_ingredient("onions", owner=user) == onion


@pytest.mark.django_db
def test_resolve_ingredient_maps_a_plural_onto_the_users_private_row(user):
    """A plural of the user's own private row resolves to it."""
    shallot = Ingredient.objects.create(ingredient_name="banana shallot", owner=user)
    assert resolve_ingredient("banana shallots", owner=user) == shallot


@pytest.mark.django_db
def test_resolve_ingredient_ignores_plurals_of_other_users_rows(user, other_user):
    """Another user's private row is invisible, plural or not."""
    theirs = Ingredient.objects.create(ingredient_name="banana shallot", owner=other_user)
    mine = resolve_ingredient("banana shallots", owner=user)
    assert mine != theirs
    assert mine.owner == user


@pytest.mark.django_db
def test_find_ingredient_matches_plurals(make_ingredient, user):
    """`find_ingredient`, the editor's no-create lookup, knows plurals too."""
    tomato = make_ingredient("tomato")
    assert find_ingredient("tomatoes", owner=user) == tomato
