"""Tests for migration 0008: sanitize existing yaml_filename values."""

import importlib

import pytest


def _get_migration():
    return importlib.import_module("recipes.migrations.0008_sanitize_yaml_filenames")


def test_migration_0008_has_runpython_operation():
    """Migration 0008 must contain exactly one RunPython operation."""
    from django.db.migrations.operations.special import RunPython

    m = _get_migration()
    run_python_ops = [op for op in m.Migration.operations if isinstance(op, RunPython)]
    assert len(run_python_ops) == 1


@pytest.mark.django_db
def test_migration_0008_sanitizes_unsanitized_rows(user):
    """_sanitize_yaml_filenames updates rows whose yaml_filename contains reserved chars."""
    from unittest.mock import MagicMock

    from recipes.models import Recipe

    m = _get_migration()
    fn = m._sanitize_yaml_filenames

    # Bypass model.save() to plant an unsanitized value
    recipe = Recipe.objects.create(recipe_name="Legacy Raw", owner=user, yaml_filename="")
    Recipe.objects.filter(pk=recipe.pk).update(yaml_filename="foo!bar.yml")

    apps = MagicMock()
    apps.get_model.return_value = Recipe
    fn(apps, MagicMock())

    recipe.refresh_from_db()
    assert recipe.yaml_filename == "foobar.yml"


@pytest.mark.django_db
def test_migration_0008_leaves_clean_rows_unchanged(user):
    """_sanitize_yaml_filenames does not alter already-clean yaml_filename values."""
    from unittest.mock import MagicMock

    from recipes.models import Recipe

    m = _get_migration()
    fn = m._sanitize_yaml_filenames

    recipe = Recipe.objects.create(
        recipe_name="Already Clean", owner=user, yaml_filename="clean_recipe.yml"
    )

    apps = MagicMock()
    apps.get_model.return_value = Recipe
    fn(apps, MagicMock())

    recipe.refresh_from_db()
    assert recipe.yaml_filename == "clean_recipe.yml"


@pytest.mark.django_db
def test_migration_0008_aborts_on_duplicate_after_sanitization(user):
    """_sanitize_yaml_filenames raises RuntimeError when two rows collapse to same filename."""
    from unittest.mock import MagicMock

    from recipes.models import Recipe

    m = _get_migration()
    fn = m._sanitize_yaml_filenames

    r1 = Recipe.objects.create(recipe_name="Recipe One", owner=user, yaml_filename="")
    r2 = Recipe.objects.create(recipe_name="Recipe Two", owner=user, yaml_filename="")
    # Plant two values that both sanitize to "foobar.yml"
    Recipe.objects.filter(pk=r1.pk).update(yaml_filename="foo!bar.yml")
    Recipe.objects.filter(pk=r2.pk).update(yaml_filename="foo@bar.yml")

    apps = MagicMock()
    apps.get_model.return_value = Recipe
    with pytest.raises(RuntimeError, match="foobar.yml"):
        fn(apps, MagicMock())

    # Neither row must have been modified
    r1.refresh_from_db()
    r2.refresh_from_db()
    assert r1.yaml_filename == "foo!bar.yml"
    assert r2.yaml_filename == "foo@bar.yml"


@pytest.mark.django_db
def test_migration_0008_blank_filenames_collision_detected(user):
    """Two blank yaml_filename rows whose names both map to same safe filename abort migration."""
    from unittest.mock import MagicMock

    from recipes.models import Recipe

    m = _get_migration()
    fn = m._sanitize_yaml_filenames

    # "My Recipe!" and "My Recipe@" both strip to "My Recipe.yml"
    r1 = Recipe.objects.create(recipe_name="My Recipe!", owner=user, yaml_filename="")
    r2 = Recipe.objects.create(recipe_name="My Recipe@", owner=user, yaml_filename="")

    apps = MagicMock()
    apps.get_model.return_value = Recipe
    with pytest.raises(RuntimeError):
        fn(apps, MagicMock())

    # Neither row modified
    r1.refresh_from_db()
    r2.refresh_from_db()
    assert r1.yaml_filename == ""
    assert r2.yaml_filename == ""


@pytest.mark.django_db
def test_migration_0008_blank_vs_nonempty_collision_detected(user):
    """Blank yaml_filename row colliding with a non-blank row aborts migration."""
    from unittest.mock import MagicMock

    from recipes.models import Recipe

    m = _get_migration()
    fn = m._sanitize_yaml_filenames

    # blank row: effective filename = safe_filename("Soup") = "Soup.yml"
    Recipe.objects.create(recipe_name="Soup", owner=user, yaml_filename="")
    # non-blank row: sanitizes to "Soup.yml"
    r2 = Recipe.objects.create(recipe_name="Soup Two", owner=user, yaml_filename="")
    Recipe.objects.filter(pk=r2.pk).update(yaml_filename="Soup.yml")

    apps = MagicMock()
    apps.get_model.return_value = Recipe
    with pytest.raises(RuntimeError):
        fn(apps, MagicMock())


@pytest.mark.django_db
def test_migration_0008_non_colliding_blank_filenames_pass(user):
    """Multiple blank yaml_filename rows with distinct names do not abort migration."""
    from unittest.mock import MagicMock

    from recipes.models import Recipe

    m = _get_migration()
    fn = m._sanitize_yaml_filenames

    Recipe.objects.create(recipe_name="Alpha Soup", owner=user, yaml_filename="")
    Recipe.objects.create(recipe_name="Beta Stew", owner=user, yaml_filename="")

    apps = MagicMock()
    apps.get_model.return_value = Recipe
    fn(apps, MagicMock())  # must not raise


def test_migration_0008_sanitize_stem_handles_reserved_with_dotted_segments():
    """Frozen _sanitize_stored_filename_mig prefixes reserved names before dotted segments."""
    m = _get_migration()
    fn = m._sanitize_stored_filename_mig

    assert fn("CON.v2.yml") == "_CON.v2.yml"
    assert fn("NUL.backup.yaml") == "_NUL.backup.yaml"
    assert fn("LPT1.old.yml") == "_LPT1.old.yml"
    # Non-reserved prefix not affected
    assert fn("my.CON.yml") == "my.CON.yml"
