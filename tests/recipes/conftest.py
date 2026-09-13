"""Shared fixtures for recipe app tests."""

import pytest

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step


@pytest.fixture
def other_user(db):
    """A second user, for owner-scoping assertions."""
    from django.contrib.auth.models import User

    return User.objects.create_user(username="someone-else", password="x")


@pytest.fixture
def make_ingredient(db):
    def _make(name: str) -> Ingredient:
        return Ingredient.objects.create(ingredient_name=name)

    return _make


@pytest.fixture
def make_recipe(db):
    def _make(*, owner, name: str) -> Recipe:
        return Recipe.objects.create(recipe_name=name, owner=owner, servings=4)

    return _make


@pytest.fixture
def add_ingredient(db):
    """Attach an ingredient to a recipe, creating a default group on demand."""

    def _add(*, recipe, ingredient, substitute=None) -> IngredientInRecipe:
        group, _ = IngredientGroup.objects.get_or_create(
            recipe=recipe, group_name="Main", defaults={"index_in_sequence": 0}
        )
        return IngredientInRecipe.objects.create(
            ingredient=ingredient,
            substitute=substitute,
            ingredient_group=group,
            index_in_sequence=IngredientInRecipe.objects.filter(ingredient_group=group).count(),
        )

    return _add


@pytest.fixture
def add_step(db):
    def _add(*, recipe, text: str) -> Step:
        return Step.objects.create(
            recipe=recipe,
            step_text=text,
            index_in_sequence=Step.objects.filter(recipe=recipe).count(),
        )

    return _add


@pytest.fixture
def without_ci_name_constraint(db):
    """Drop the case-insensitive ingredient-name index for one test.

    `find_ingredient_duplicates` exists to clean up databases created before
    that constraint, so exercising it means reproducing that state. SQLite runs
    the DDL inside the test's transaction, so it is rolled back afterwards.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX ingredient_name_ci_unique")
