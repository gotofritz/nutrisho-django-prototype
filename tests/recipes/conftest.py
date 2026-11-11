"""Shared fixtures for recipe app tests."""

import pytest

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step
from recipes.services.name_resolution import find_unit


@pytest.fixture
def other_user(db):
    """A second user, for owner-scoping assertions."""
    from django.contrib.auth.models import User

    return User.objects.create_user(username="someone-else", password="x")


@pytest.fixture
def make_ingredient(db):
    """Make ingredient."""

    def _make(name: str, *, plural_name: str = "") -> Ingredient:
        return Ingredient.objects.create(ingredient_name=name, plural_name=plural_name)

    return _make


@pytest.fixture
def make_recipe(db):
    """Make recipe."""

    def _make(*, owner, name: str) -> Recipe:
        return Recipe.objects.create(recipe_name=name, owner=owner, servings=4)

    return _make


@pytest.fixture
def add_ingredient(db):
    """Attach an ingredient to a recipe, creating a default group on demand.

    `unit` is typed text, resolved to the vocabulary as the editor would (#67).
    """

    def _add(*, recipe, ingredient, substitute=None, quantity=None, unit="") -> IngredientInRecipe:
        group, _ = IngredientGroup.objects.get_or_create(
            recipe=recipe, group_name="Main", defaults={"index_in_sequence": 0}
        )
        return IngredientInRecipe.objects.create(
            ingredient=ingredient,
            substitute=substitute,
            quantity=quantity,
            unit=find_unit(unit),
            ingredient_group=group,
            index_in_sequence=IngredientInRecipe.objects.filter(ingredient_group=group).count(),
        )

    return _add


@pytest.fixture
def add_step(db):
    """Add step."""

    def _add(*, recipe, text: str, title: str = "") -> Step:
        return Step.objects.create(
            recipe=recipe,
            step_text=text,
            step_title=title,
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


@pytest.fixture
def migrate_to(transactional_db):
    """Migrate the test database to a past state; afterwards, back to the latest.

    Returns a function taking a list of `(app, migration)` targets and giving
    the historical apps registry at that state. Without the final step, the
    tests after this one would run against an old schema.
    """
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    def _migrate(target: list[tuple[str, str]]):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    yield _migrate
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())
