"""Tests for recipes models."""

import pytest

from recipes.models import Recipe


@pytest.mark.django_db
def test_recipe_creation(user):
    recipe = Recipe.objects.create(recipe_name="Test Recipe", owner=user)
    assert recipe.recipe_name == "Test Recipe"
    assert recipe.pk is not None


@pytest.mark.django_db
def test_recipe_natural_key(user):
    recipe = Recipe.objects.create(recipe_name="Pasta Carbonara", owner=user)
    assert recipe.natural_key() == "Pasta Carbonara"


@pytest.mark.django_db
def test_recipe_absolute_url(user):
    recipe = Recipe.objects.create(recipe_name="Soup", owner=user)
    assert recipe.get_absolute_url() == f"/recipes/{recipe.pk}/"
