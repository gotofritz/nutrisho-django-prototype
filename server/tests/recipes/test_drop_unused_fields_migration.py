"""Tests for migration 0027: drop `Source`, `Step.duration` and `Step.extra_info` (#65)."""

import importlib
from datetime import timedelta

import pytest
from django.core.management.base import CommandError

MIGRATION = importlib.import_module("recipes.migrations.0027_drop_unused_source_and_step_fields")
BEFORE = [("recipes", "0026_seed_units")]
AFTER = [("recipes", "0027_drop_unused_source_and_step_fields")]


def _recipe_with_a_step(old, user):
    recipe = old.get_model("recipes", "Recipe").objects.create(
        recipe_name="Old", owner_id=user.pk, servings=1
    )
    step = old.get_model("recipes", "Step").objects.create(
        recipe=recipe, step_text="Boil", index_in_sequence=0
    )
    return recipe, step


@pytest.mark.django_db(transaction=True)
def test_empty_columns_are_dropped_and_the_rest_survives(user, migrate_to):
    """Nothing held, nothing lost: the recipe and its step come through."""
    old = migrate_to(BEFORE)
    recipe, step = _recipe_with_a_step(old, user)
    new = migrate_to(AFTER)
    assert new.get_model("recipes", "Step").objects.get(pk=step.pk).step_text == "Boil"
    assert new.get_model("recipes", "Recipe").objects.filter(pk=recipe.pk).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("column", ["extra_info", "duration", "Recipe.source"])
def test_a_column_holding_data_stops_the_migration(user, migrate_to, column):
    """Admin could have written them; nothing is dropped silently."""
    old = migrate_to(BEFORE)
    recipe, step = _recipe_with_a_step(old, user)
    source = old.get_model("recipes", "Source")
    if column == "extra_info":
        step.extra_info = "Use a sharp knife"
    elif column == "duration":
        step.duration = timedelta(minutes=5)
    else:
        recipe.source = source.objects.create(short_name="Moro", source="isbn")
    recipe.save()
    step.save()
    with pytest.raises(CommandError, match=column):
        MIGRATION.refuse_to_drop_data(old, None)
    # Clear it so the fixture can migrate forward again.
    recipe.delete()
    source.objects.all().delete()
