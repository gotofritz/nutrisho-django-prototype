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

    `unit` is typed text, resolved to the vocabulary as the editor would (#67):
    the global units and the recipe owner's own (#154).
    """

    def _add(*, recipe, ingredient, substitute=None, quantity=None, unit="") -> IngredientInRecipe:
        group, _ = IngredientGroup.objects.get_or_create(
            recipe=recipe, group_name="Main", defaults={"index_in_sequence": 0}
        )
        return IngredientInRecipe.objects.create(
            ingredient=ingredient,
            substitute=substitute,
            quantity=quantity,
            unit=find_unit(unit, owner=recipe.owner),
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
def pre_rename_apps(db):
    """The models as of migration 0027, `Tag.recipe` not yet `recipes`, with UUID recipe keys.

    Tests that call an older data migration's function on the current database
    pass it these, as the migration itself would, instead of the live models.
    Migrating back to that migration is not an option: the seeded cuisine tree
    cannot be reversed past 0020. The recipe keys of 0033 (#156) are laid over
    them, so the models read today's recipe ids.
    """
    from django.db import connection
    from django.db.migrations.loader import MigrationLoader

    loader = MigrationLoader(connection)
    state = loader.project_state(("recipes", "0027_drop_unused_source_and_step_fields"))
    for operation in loader.get_migration("recipes", "0033_recipe_uuid_keys").operations:
        operation.state_forwards("recipes", state)
    return state.apps


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


@pytest.fixture
def rich_recipe(user):
    """A recipe that uses every field an export carries, with two groups and markup (#78).

    Its first ingredient is private to `user` and has display data of its own;
    its second row's unit is legacy free text. A second recipe sits in the trash.
    """
    from datetime import UTC, datetime
    from decimal import Decimal

    from recipes.models import Tag
    from recipes.services.name_resolution import find_cuisine

    recipe = Recipe.objects.create(
        recipe_name="<u>Pasta</u> alla Norma",
        short_description="Rich\nand <i>warm</i>",
        owner=user,
        servings=4,
        source_instance="https://example.com/norma",
        cuisine=find_cuisine("med.italy.sicily"),
    )
    Recipe.objects.filter(pk=recipe.pk).update(created_date=datetime(2024, 1, 2, 3, 4, tzinfo=UTC))
    recipe.refresh_from_db()
    recipe.tags.add(
        Tag.objects.create(tag="dinner"), Tag.objects.create(tag="favourite", owner=user)
    )
    Step.objects.create(
        recipe=recipe,
        step_title="Prep",
        step_text="Chop the <b>aubergine</b>.",
        index_in_sequence=0,
    )
    Step.objects.create(recipe=recipe, step_text="Fry.", index_in_sequence=1)
    sauce = IngredientGroup.objects.create(recipe=recipe, group_name="Sauce", index_in_sequence=0)
    aubergine = Ingredient.objects.create(
        ingredient_name="aubergine-x",
        owner=user,
        plural_name="aubergines-x",
        family="VEG",
        dietary_constraint="VGN",
    )
    IngredientInRecipe.objects.create(
        ingredient_group=sauce,
        index_in_sequence=0,
        ingredient=aubergine,
        substitute=Ingredient.objects.create(ingredient_name="courgette-x"),
        quantity=Decimal("1.50"),
        unit=find_unit("kg", owner=None),
        preparation="cubed",
        note="firm ones",
    )
    IngredientInRecipe.objects.create(
        ingredient_group=sauce,
        index_in_sequence=1,
        ingredient=Ingredient.objects.create(ingredient_name="basil-x"),
        legacy_unit="handful",
        preparation="torn",
    )
    pasta = IngredientGroup.objects.create(recipe=recipe, group_name="Pasta", index_in_sequence=1)
    IngredientInRecipe.objects.create(
        ingredient_group=pasta,
        index_in_sequence=0,
        ingredient=Ingredient.objects.create(ingredient_name="rigatoni-x"),
        quantity=Decimal(400),
        unit=find_unit("g", owner=None),
    )
    trashed = Recipe.objects.create(recipe_name="Old soup", owner=user, servings=2)
    Recipe.objects.filter(pk=trashed.pk).update(deleted_at=datetime(2025, 5, 6, tzinfo=UTC))
    return recipe
