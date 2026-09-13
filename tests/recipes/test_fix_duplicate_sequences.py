"""Tests for fix_duplicate_sequences management command."""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from recipes.management.commands.fix_duplicate_sequences import Command
from recipes.models import IngredientGroup, IngredientInRecipe, Recipe


@pytest.fixture
def recipe(user, db):
    return Recipe.objects.create(recipe_name="Dupe Recipe", owner=user)


@pytest.fixture
def group(recipe):
    return IngredientGroup.objects.create(recipe=recipe, group_name="G0", index_in_sequence=0)


@pytest.mark.django_db
def test_no_duplicates_reports_clean(recipe, group, capsys):
    call_command("fix_duplicate_sequences")
    assert "No duplicates found" in capsys.readouterr().out


@pytest.mark.django_db
def test_no_duplicates_multiple_groups(recipe, capsys):
    IngredientGroup.objects.create(recipe=recipe, group_name="G0", index_in_sequence=0)
    IngredientGroup.objects.create(recipe=recipe, group_name="G1", index_in_sequence=1)
    call_command("fix_duplicate_sequences")
    assert "No duplicates found" in capsys.readouterr().out


def _mock_group(recipe_id, group_id, index):
    g = MagicMock(spec=IngredientGroup)
    g.id = group_id
    g.recipe_id = recipe_id
    g.index_in_sequence = index
    return g


def _mock_iir(group_id, iir_id, index):
    i = MagicMock(spec=IngredientInRecipe)
    i.id = iir_id
    i.ingredient_group_id = group_id
    i.index_in_sequence = index
    return i


def _group_cmd():
    cmd = Command()
    cmd.stdout = StringIO()  # ty: ignore[invalid-assignment]
    return cmd


def _patched_groups(recipe_ids, groups_by_recipe):
    """Context manager mocking IngredientGroup.objects for _fix_ingredient_groups."""

    vl_mock = MagicMock()
    vl_mock.distinct.return_value = recipe_ids

    def filter_side_effect(**kwargs):
        rid = kwargs.get("recipe_id")
        qs = MagicMock()
        qs.order_by.return_value = groups_by_recipe.get(rid, [])
        return qs

    return (
        patch.object(IngredientGroup.objects, "values_list", return_value=vl_mock),
        patch.object(IngredientGroup.objects, "filter", side_effect=filter_side_effect),
    )


def _patched_iirs(group_ids, iirs_by_group):
    vl_mock = MagicMock()
    vl_mock.distinct.return_value = group_ids

    def filter_side_effect(**kwargs):
        gid = kwargs.get("ingredient_group_id")
        qs = MagicMock()
        qs.order_by.return_value = iirs_by_group.get(gid, [])
        return qs

    return (
        patch.object(IngredientInRecipe.objects, "values_list", return_value=vl_mock),
        patch.object(IngredientInRecipe.objects, "filter", side_effect=filter_side_effect),
    )


def test_fix_groups_reassigns_duplicate_index():
    g1 = _mock_group(1, 10, 0)
    g2 = _mock_group(1, 11, 0)  # duplicate
    cmd = _group_cmd()

    vl_patch, filter_patch = _patched_groups([1], {1: [g1, g2]})
    with vl_patch, filter_patch:
        fixes = cmd._fix_ingredient_groups(dry_run=False)

    assert fixes == 1
    assert g2.index_in_sequence == 1
    g2.save.assert_called_once_with(update_fields=["index_in_sequence"])


def test_fix_groups_dry_run_does_not_save():
    g1 = _mock_group(1, 10, 0)
    g2 = _mock_group(1, 11, 0)
    cmd = _group_cmd()

    vl_patch, filter_patch = _patched_groups([1], {1: [g1, g2]})
    with vl_patch, filter_patch:
        fixes = cmd._fix_ingredient_groups(dry_run=True)

    assert fixes == 1
    g2.save.assert_not_called()


def test_fix_iir_reassigns_duplicate_index():
    i1 = _mock_iir(5, 20, 0)
    i2 = _mock_iir(5, 21, 0)  # duplicate
    cmd = _group_cmd()

    vl_patch, filter_patch = _patched_iirs([5], {5: [i1, i2]})
    with vl_patch, filter_patch:
        fixes = cmd._fix_ingredient_in_recipe(dry_run=False)

    assert fixes == 1
    assert i2.index_in_sequence == 1
    i2.save.assert_called_once_with(update_fields=["index_in_sequence"])


def test_fix_iir_dry_run_does_not_save():
    i1 = _mock_iir(5, 20, 0)
    i2 = _mock_iir(5, 21, 0)
    cmd = _group_cmd()

    vl_patch, filter_patch = _patched_iirs([5], {5: [i1, i2]})
    with vl_patch, filter_patch:
        fixes = cmd._fix_ingredient_in_recipe(dry_run=True)

    assert fixes == 1
    i2.save.assert_not_called()


def test_fix_three_dupes_reassigns_sequentially():
    i1 = _mock_iir(5, 20, 0)
    i2 = _mock_iir(5, 21, 0)
    i3 = _mock_iir(5, 22, 0)
    cmd = _group_cmd()

    vl_patch, filter_patch = _patched_iirs([5], {5: [i1, i2, i3]})
    with vl_patch, filter_patch:
        fixes = cmd._fix_ingredient_in_recipe(dry_run=False)

    assert fixes == 2
    assert i2.index_in_sequence == 1
    assert i3.index_in_sequence == 2
