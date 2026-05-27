"""Tests for migration 0007: unique sequence constraints with duplicate-detection pre-check."""

import importlib
from unittest.mock import MagicMock


def _get_migration():
    return importlib.import_module("recipes.migrations.0007_unique_sequence_constraints")


def _make_apps_with_duplicates(has_group_dups: bool = False, has_iir_dups: bool = False):
    """Return a mock apps object whose querysets contain duplicate index_in_sequence rows."""
    apps = MagicMock()

    if has_group_dups:
        grp1, grp2 = MagicMock(), MagicMock()
        grp1.recipe_id = 1
        grp1.index_in_sequence = 1
        grp2.recipe_id = 1
        grp2.index_in_sequence = 1  # duplicate
        apps.get_model.side_effect = lambda app, model: {
            ("recipes", "IngredientGroup"): _mock_qs([grp1, grp2]),
            ("recipes", "IngredientInRecipe"): _mock_qs([]),
        }.get((app, model), _mock_qs([]))
    elif has_iir_dups:
        iir1, iir2 = MagicMock(), MagicMock()
        iir1.ingredient_group_id = 5
        iir1.index_in_sequence = 2
        iir2.ingredient_group_id = 5
        iir2.index_in_sequence = 2  # duplicate
        apps.get_model.side_effect = lambda app, model: {
            ("recipes", "IngredientGroup"): _mock_qs([]),
            ("recipes", "IngredientInRecipe"): _mock_qs([iir1, iir2]),
        }.get((app, model), _mock_qs([]))
    else:
        apps.get_model.side_effect = lambda app, model: _mock_qs([])

    return apps


def _mock_qs(rows):
    """Return a mock model whose .objects.all() yields rows."""
    model = MagicMock()
    model.objects.all.return_value = iter(rows)
    return model


def test_migration_0007_has_check_before_add_constraint():
    """RunPython pre-check must come before the AddConstraint operations."""
    from django.db.migrations.operations.special import RunPython

    migration = _get_migration()
    ops = migration.Migration.operations
    run_python_indices = [i for i, op in enumerate(ops) if isinstance(op, RunPython)]
    add_constraint_indices = [i for i, op in enumerate(ops) if type(op).__name__ == "AddConstraint"]
    assert run_python_indices, "Migration 0007 must have a RunPython pre-check"
    assert min(run_python_indices) < min(add_constraint_indices), (
        "RunPython pre-check must come before AddConstraint operations"
    )


def test_migration_0007_clean_db_passes():
    """Pre-check raises nothing when there are no duplicate rows."""
    migration = _get_migration()
    check_fn = _get_check_fn(migration)
    apps = _make_apps_with_duplicates(False, False)
    schema_editor = MagicMock()
    check_fn(apps, schema_editor)  # must not raise


def test_migration_0007_duplicate_group_index_raises():
    """Pre-check raises RuntimeError when IngredientGroup has duplicate (recipe, index) rows."""
    migration = _get_migration()
    check_fn = _get_check_fn(migration)
    apps = _make_apps_with_duplicates(has_group_dups=True)
    schema_editor = MagicMock()
    import pytest

    with pytest.raises(RuntimeError, match="duplicate"):
        check_fn(apps, schema_editor)


def test_migration_0007_duplicate_iir_index_raises():
    """Pre-check raises RuntimeError when IngredientInRecipe has duplicate (group, index) rows."""
    migration = _get_migration()
    check_fn = _get_check_fn(migration)
    apps = _make_apps_with_duplicates(has_iir_dups=True)
    schema_editor = MagicMock()
    import pytest

    with pytest.raises(RuntimeError, match="duplicate"):
        check_fn(apps, schema_editor)


def _get_check_fn(migration):
    """Extract the RunPython callable from migration 0007."""
    from django.db.migrations.operations.special import RunPython

    for op in migration.Migration.operations:
        if isinstance(op, RunPython):
            return op.code
    raise AssertionError("No RunPython operation found in migration 0007")
