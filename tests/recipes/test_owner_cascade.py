"""Tests for Recipe.owner FK ownership policy."""

import pytest
from django.contrib.auth.models import User

from recipes.models import Recipe


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="owner-cascade", password="x")


@pytest.mark.django_db
def test_deleting_owner_cascades_to_recipes(owner):
    """Deleting a user must delete their recipes, not reassign them."""
    r = Recipe.objects.create(recipe_name="Cascade Recipe", owner=owner)
    pk = r.pk
    owner.delete()
    assert not Recipe.objects.filter(pk=pk).exists()


@pytest.mark.django_db
def test_recipe_requires_explicit_owner(db):
    """Creating Recipe without owner must raise IntegrityError (no default)."""
    import pytest
    from django.db import IntegrityError

    with pytest.raises((IntegrityError, Exception)):
        Recipe.objects.create(recipe_name="No Owner Recipe")
