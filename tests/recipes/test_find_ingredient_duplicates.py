"""Tests for the find_ingredient_duplicates management command."""

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_reports_a_clean_database(make_ingredient, capsys):
    make_ingredient("onion")
    call_command("find_ingredient_duplicates")
    assert "No case-insensitive duplicates found" in capsys.readouterr().out


@pytest.mark.django_db
def test_lists_each_clashing_group(without_ci_name_constraint, make_ingredient, capsys):
    onion = make_ingredient("onion")
    capital = make_ingredient("Onion")
    call_command("find_ingredient_duplicates")
    out = capsys.readouterr().out
    assert f"Onion (id={capital.pk})" in out
    assert f"onion (id={onion.pk})" in out
    assert "1 duplicate group" in out


@pytest.mark.django_db
def test_counts_multiple_groups(without_ci_name_constraint, make_ingredient, capsys):
    for name in ("onion", "Onion", "carrot", "Carrot"):
        make_ingredient(name)
    call_command("find_ingredient_duplicates")
    assert "2 duplicate groups" in capsys.readouterr().out


def _guard():
    """The pre-flight check migration 0013 runs before adding its constraint."""
    import importlib

    module = importlib.import_module("recipes.migrations.0013_ingredient_ingredient_name_ci_unique")
    return module.reject_case_insensitive_duplicates


@pytest.mark.django_db
def test_migration_guard_passes_on_a_clean_database(make_ingredient):
    from django.apps import apps

    make_ingredient("onion")
    make_ingredient("carrot")
    _guard()(apps, None)


@pytest.mark.django_db
def test_migration_guard_names_the_clashes_instead_of_crashing(
    without_ci_name_constraint, make_ingredient
):
    """A raw IntegrityError mid-migrate tells the owner nothing about what to do."""
    from django.apps import apps
    from django.core.management.base import CommandError

    make_ingredient("onion")
    make_ingredient("Onion")
    make_ingredient("carrot")
    with pytest.raises(CommandError) as excinfo:
        _guard()(apps, None)
    message = str(excinfo.value)
    assert "Onion, onion" in message
    assert "find_ingredient_duplicates" in message
    assert "/recipes/ingredients/manage/" in message
    assert "carrot" not in message


@pytest.mark.django_db
def test_reports_no_plural_pairs_on_a_clean_database(make_ingredient, capsys):
    make_ingredient("onion")
    call_command("find_ingredient_duplicates")
    assert "No singular/plural pairs found" in capsys.readouterr().out


@pytest.mark.django_db
def test_lists_each_singular_plural_pair(make_ingredient, capsys):
    """A plural is a display form, so an `onions` row is bad data (issue #24)."""
    onion = make_ingredient("onion")
    onions = make_ingredient("onions")
    call_command("find_ingredient_duplicates")
    out = capsys.readouterr().out
    assert f"onion (id={onion.pk})" in out
    assert f"onions (id={onions.pk})" in out
    assert "1 singular/plural pair" in out
    assert "/recipes/ingredients/manage/" in out


@pytest.mark.django_db
def test_counts_multiple_plural_pairs(make_ingredient, capsys):
    for name in ("onion", "onions", "tomato", "tomatoes"):
        make_ingredient(name)
    call_command("find_ingredient_duplicates")
    assert "2 singular/plural pairs" in capsys.readouterr().out


@pytest.mark.django_db
def test_reports_both_classes_together(without_ci_name_constraint, make_ingredient, capsys):
    for name in ("carrot", "Carrot", "onion", "onions"):
        make_ingredient(name)
    call_command("find_ingredient_duplicates")
    out = capsys.readouterr().out
    assert "1 duplicate group" in out
    assert "1 singular/plural pair" in out
