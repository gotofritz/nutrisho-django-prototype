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


# --- 0032: private units (#154) -------------------------------------------------

BEFORE_PRIVATE = [("recipes", "0031_api_token")]
AFTER_PRIVATE = [("recipes", "0032_private_units")]


def _rows_with_units(apps, *, user, units):
    """One recipe of `user`'s with a row for each of `units`, in order."""
    recipe = apps.get_model("recipes", "Recipe").objects.create(
        recipe_name="Jam", owner_id=user.pk, servings=1
    )
    group = apps.get_model("recipes", "IngredientGroup").objects.create(
        recipe=recipe, group_name="", index_in_sequence=0
    )
    ingredient = apps.get_model("recipes", "Ingredient").objects.create(
        ingredient_name="strawberry"
    )
    return [
        apps.get_model("recipes", "IngredientInRecipe").objects.create(
            ingredient=ingredient, ingredient_group=group, index_in_sequence=index, unit=unit
        )
        for index, unit in enumerate(units)
    ]


@pytest.mark.django_db(transaction=True)
def test_existing_units_become_global_and_rows_keep_them(user, migrate_to):
    """Every unit there was is global afterwards, and no row loses its unit."""
    old = migrate_to(BEFORE_PRIVATE)
    unit = old.get_model("recipes", "Unit").objects.create(name="bushel", dimension="volume")
    (row,) = _rows_with_units(old, user=user, units=[unit])

    new = migrate_to(AFTER_PRIVATE)
    assert new.get_model("recipes", "Unit").objects.get(pk=unit.pk).owner_id is None
    assert new.get_model("recipes", "IngredientInRecipe").objects.get(pk=row.pk).unit_id == unit.pk


@pytest.mark.django_db(transaction=True)
def test_reversing_turns_private_units_back_into_legacy_text(user, other_user, migrate_to):
    """Going back to one global list, a private unit's rows keep its name as text."""
    new = migrate_to(AFTER_PRIVATE)
    units = new.get_model("recipes", "Unit").objects
    mine = units.create(name="punnet", owner_id=user.pk)
    units.create(name="Punnet", owner_id=other_user.pk)
    global_unit = units.create(name="bushel", dimension="volume")
    private_row, global_row = _rows_with_units(new, user=user, units=[mine, global_unit])

    old = migrate_to(BEFORE_PRIVATE)
    rows = old.get_model("recipes", "IngredientInRecipe").objects
    reverted = rows.get(pk=private_row.pk)
    assert (reverted.unit_id, reverted.legacy_unit) == (None, "punnet")
    assert rows.get(pk=global_row.pk).unit_id == global_unit.pk
    assert not old.get_model("recipes", "Unit").objects.filter(name__iexact="punnet").exists()
