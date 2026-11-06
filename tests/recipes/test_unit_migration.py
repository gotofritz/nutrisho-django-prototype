"""Tests for migrations 0025 and 0026: the unit vocabulary (#67)."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("recipes", "0024_ingredient_alias")]
AFTER = [("recipes", "0026_seed_units")]


def _migrate(target: list[tuple[str, str]]):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.mark.django_db(transaction=True)
def test_typed_units_survive_as_legacy_text_and_the_vocabulary_is_seeded(user):
    """The old text moves to `legacy_unit` untouched; no row is pointed at a unit yet."""
    old = _migrate(BEFORE)
    recipe = old.get_model("recipes", "Recipe").objects.create(
        recipe_name="Old", owner_id=user.pk, servings=1
    )
    group = old.get_model("recipes", "IngredientGroup").objects.create(
        recipe=recipe, group_name="", index_in_sequence=0
    )
    ingredient = old.get_model("recipes", "Ingredient").objects.create(ingredient_name="salt")
    row = old.get_model("recipes", "IngredientInRecipe").objects.create(
        ingredient=ingredient, ingredient_group=group, index_in_sequence=0, unit="Tbsp"
    )

    new = _migrate(AFTER)
    migrated = new.get_model("recipes", "IngredientInRecipe").objects.get(pk=row.pk)
    assert migrated.legacy_unit == "Tbsp"
    assert migrated.unit_id is None
    unit = new.get_model("recipes", "Unit")
    assert unit.objects.get(name="tbsp").aliases.filter(alias_name="tablespoon").exists()


@pytest.mark.django_db(transaction=True)
def test_reversing_writes_the_canonical_unit_back_as_text(user):
    """Going back to free text keeps what the vocabulary held."""
    new = _migrate(AFTER)
    recipe = new.get_model("recipes", "Recipe").objects.create(
        recipe_name="New", owner_id=user.pk, servings=1
    )
    group = new.get_model("recipes", "IngredientGroup").objects.create(
        recipe=recipe, group_name="", index_in_sequence=0
    )
    ingredient = new.get_model("recipes", "Ingredient").objects.create(ingredient_name="salt")
    row_model = new.get_model("recipes", "IngredientInRecipe")
    normalised = row_model.objects.create(
        ingredient=ingredient,
        ingredient_group=group,
        index_in_sequence=0,
        # A transactional test may start on a flushed table, so not `get`.
        unit=new.get_model("recipes", "Unit").objects.get_or_create(
            name="tbsp", defaults={"dimension": "volume", "plural_name": "tbsp"}
        )[0],
    )
    legacy = row_model.objects.create(
        ingredient=ingredient, ingredient_group=group, index_in_sequence=1, legacy_unit="tbso"
    )

    old = _migrate(BEFORE)
    rows = old.get_model("recipes", "IngredientInRecipe").objects
    assert rows.get(pk=normalised.pk).unit == "tbsp"
    assert rows.get(pk=legacy.pk).unit == "tbso"
    _migrate(AFTER)
