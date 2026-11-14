"""Tests for migrations 0025 and 0026: the unit vocabulary (#67)."""

import pytest

BEFORE = [("recipes", "0024_ingredient_alias")]
AFTER = [("recipes", "0026_seed_units")]


@pytest.mark.django_db(transaction=True)
def test_typed_units_survive_as_legacy_text_and_the_vocabulary_is_seeded(user, migrate_to):
    """The old text moves to `legacy_unit` untouched; no row is pointed at a unit yet."""
    old = migrate_to(BEFORE)
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

    new = migrate_to(AFTER)
    migrated = new.get_model("recipes", "IngredientInRecipe").objects.get(pk=row.pk)
    assert migrated.legacy_unit == "Tbsp"
    assert migrated.unit_id is None
    unit = new.get_model("recipes", "Unit")
    assert unit.objects.get(name="tbsp").aliases.filter(alias_name="tablespoon").exists()


@pytest.mark.django_db(transaction=True)
def test_reversing_writes_the_canonical_unit_back_as_text(user, migrate_to):
    """Going back to free text keeps what the vocabulary held."""
    new = migrate_to(AFTER)
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

    old = migrate_to(BEFORE)
    rows = old.get_model("recipes", "IngredientInRecipe").objects
    assert rows.get(pk=normalised.pk).unit == "tbsp"
    assert rows.get(pk=legacy.pk).unit == "tbso"
    migrate_to(AFTER)
