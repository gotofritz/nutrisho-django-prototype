"""Unit tests for sequencing helpers: remove_and_compact, move_in_sequence."""

import pytest

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step
from recipes.utils.sequencing import insert_at_index, move_in_sequence, remove_and_compact


@pytest.fixture
def recipe(user, db):
    return Recipe.objects.create(recipe_name="Seq Recipe", owner=user)


@pytest.fixture
def group(recipe):
    return IngredientGroup.objects.create(recipe=recipe, group_name="G", index_in_sequence=0)


def _make_iir(group, index):
    ing = Ingredient.objects.create(ingredient_name=f"ing-seq-{index}")
    return IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=index
    )


# --- remove_and_compact ---


@pytest.mark.django_db
def test_remove_and_compact_closes_gap(group):
    iir0 = _make_iir(group, 0)
    iir1 = _make_iir(group, 1)
    iir2 = _make_iir(group, 2)
    siblings = IngredientInRecipe.objects.filter(ingredient_group=group)
    remove_and_compact(siblings=siblings, instance=iir1)
    iir0.refresh_from_db()
    iir2.refresh_from_db()
    assert iir0.index_in_sequence == 0
    assert iir2.index_in_sequence == 1
    assert not IngredientInRecipe.objects.filter(pk=iir1.pk).exists()


@pytest.mark.django_db
def test_remove_and_compact_last_item_no_gaps(group):
    iir0 = _make_iir(group, 0)
    iir1 = _make_iir(group, 1)
    siblings = IngredientInRecipe.objects.filter(ingredient_group=group)
    remove_and_compact(siblings=siblings, instance=iir1)
    iir0.refresh_from_db()
    assert iir0.index_in_sequence == 0
    assert not IngredientInRecipe.objects.filter(pk=iir1.pk).exists()


@pytest.mark.django_db
def test_remove_and_compact_only_item(group):
    iir0 = _make_iir(group, 0)
    siblings = IngredientInRecipe.objects.filter(ingredient_group=group)
    remove_and_compact(siblings=siblings, instance=iir0)
    assert IngredientInRecipe.objects.filter(ingredient_group=group).count() == 0


# --- move_in_sequence ---


@pytest.mark.django_db
def test_move_up_swaps_with_predecessor(group):
    iir0 = _make_iir(group, 0)
    iir1 = _make_iir(group, 1)
    siblings = IngredientInRecipe.objects.filter(ingredient_group=group)
    move_in_sequence(siblings=siblings, instance=iir1, direction="up")
    iir0.refresh_from_db()
    iir1.refresh_from_db()
    assert iir1.index_in_sequence == 0
    assert iir0.index_in_sequence == 1


@pytest.mark.django_db
def test_move_down_swaps_with_successor(group):
    iir0 = _make_iir(group, 0)
    iir1 = _make_iir(group, 1)
    siblings = IngredientInRecipe.objects.filter(ingredient_group=group)
    move_in_sequence(siblings=siblings, instance=iir0, direction="down")
    iir0.refresh_from_db()
    iir1.refresh_from_db()
    assert iir0.index_in_sequence == 1
    assert iir1.index_in_sequence == 0


@pytest.mark.django_db
def test_move_up_at_top_is_noop(group):
    iir0 = _make_iir(group, 0)
    iir1 = _make_iir(group, 1)
    siblings = IngredientInRecipe.objects.filter(ingredient_group=group)
    move_in_sequence(siblings=siblings, instance=iir0, direction="up")
    iir0.refresh_from_db()
    iir1.refresh_from_db()
    assert iir0.index_in_sequence == 0
    assert iir1.index_in_sequence == 1


@pytest.mark.django_db
def test_move_down_at_bottom_is_noop(group):
    iir0 = _make_iir(group, 0)
    iir1 = _make_iir(group, 1)
    siblings = IngredientInRecipe.objects.filter(ingredient_group=group)
    move_in_sequence(siblings=siblings, instance=iir1, direction="down")
    iir0.refresh_from_db()
    iir1.refresh_from_db()
    assert iir0.index_in_sequence == 0
    assert iir1.index_in_sequence == 1


# --- insert_at_index ---


@pytest.mark.django_db
def test_insert_at_index_empty_siblings_assigns_zero(recipe):
    """First item into empty parent gets index_in_sequence=0."""

    step = Step(recipe=recipe, step_text="First")
    insert_at_index(
        siblings=Step.objects.filter(recipe=recipe),
        instance=step,
        requested_index=None,
        lock_parent=Recipe.objects.filter(pk=recipe.pk),
    )
    step.refresh_from_db()
    assert step.index_in_sequence == 0


@pytest.mark.django_db
def test_insert_at_index_empty_siblings_locks_parent(recipe):
    """insert_at_index must call select_for_update on lock_parent even when siblings is empty."""
    from unittest.mock import patch


    locked = []

    original_sfu = Recipe.objects.none().__class__.select_for_update

    def spy_sfu(self, *args, **kwargs):
        locked.append(self.model.__name__)
        return original_sfu(self, *args, **kwargs)

    with patch("django.db.models.QuerySet.select_for_update", spy_sfu):
        step = Step(recipe=recipe, step_text="Only")
        insert_at_index(
            siblings=Step.objects.filter(recipe=recipe),
            instance=step,
            requested_index=None,
            lock_parent=Recipe.objects.filter(pk=recipe.pk),
        )
    assert "Recipe" in locked
