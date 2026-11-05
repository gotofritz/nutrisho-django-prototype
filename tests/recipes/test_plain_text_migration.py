"""Tests for migration 0023: plain-text recipe names and descriptions (#32)."""

import importlib

import pytest
from django.apps import apps
from django.core.management.base import CommandError

from recipes.models import Recipe

MIGRATION = importlib.import_module("recipes.migrations.0023_recipe_plain_text")


@pytest.mark.django_db
def test_the_backfill_fills_both_plain_columns(user):
    """Rows saved before the columns existed get their tag-free text."""
    recipe = Recipe.objects.create(recipe_name="Soup", owner=user)
    Recipe.objects.filter(pk=recipe.pk).update(
        recipe_name="<u>Ragù</u>",
        short_description="<b>Slow</b>",
        plain_name="",
        plain_description="",
    )
    MIGRATION.backfill_plain_text(apps, None)
    recipe.refresh_from_db()
    assert (recipe.plain_name, recipe.plain_description) == ("Ragù", "Slow")


@pytest.mark.django_db
def test_names_that_differ_only_by_markup_stop_the_migration(user):
    """`Foo` and `<u>Foo</u>` for one owner are named, and nothing is renamed."""
    Recipe.objects.create(recipe_name="Foo", owner=user)
    bar = Recipe.objects.create(recipe_name="Bar", owner=user)
    Recipe.objects.filter(pk=bar.pk).update(recipe_name="<u>Foo</u>")
    with pytest.raises(CommandError, match=r"Foo, <u>Foo</u>|<u>Foo</u>, Foo"):
        MIGRATION.reject_markup_only_clashes(apps, None)
    assert Recipe.objects.filter(recipe_name="<u>Foo</u>").exists()


@pytest.mark.django_db
def test_the_same_name_for_two_owners_is_no_clash(user, other_user):
    """Uniqueness is per owner, before and after."""
    Recipe.objects.create(recipe_name="Foo", owner=user)
    Recipe.objects.create(recipe_name="<u>Foo</u>", owner=other_user)
    MIGRATION.reject_markup_only_clashes(apps, None)
