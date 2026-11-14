"""Tests for creating a recipe and saving its metadata through services (#77)."""

import pytest
from django.core.exceptions import ObjectDoesNotExist

from recipes.models import Cuisine, Recipe, Tag
from recipes.services.recipe_metadata import (
    DuplicateRecipeNameError,
    create_recipe,
    save_field,
    save_metadata,
    set_tags,
)


@pytest.fixture
def recipe(user, make_recipe) -> Recipe:
    """A recipe owned by the test user."""
    return make_recipe(owner=user, name="Soup")


def _tags(recipe: Recipe) -> list[str]:
    return sorted(recipe.tags.values_list("tag", flat=True))  # ty: ignore[unresolved-attribute]


# --- set_tags ---


@pytest.mark.django_db
def test_set_tags_replaces_them_with_the_named_ones(recipe):
    """The recipe ends with exactly the named tags, new ones private to its owner."""
    set_tags(recipe, names=["quick", "vegan"])
    set_tags(recipe, names=["vegan", "cheap"])
    assert _tags(recipe) == ["cheap", "vegan"]
    assert Tag.objects.get(tag="cheap").owner == recipe.owner


# --- create_recipe ---


@pytest.mark.django_db
def test_create_recipe_saves_it_with_owner_and_tags(user):
    """The new recipe belongs to `owner` and carries the tags."""
    created = create_recipe(
        owner=user, recipe=Recipe(recipe_name="Stew", servings=2), tag_names=["winter"]
    )
    assert created.pk is not None
    assert created.owner == user
    assert created.plain_name == "Stew"
    assert _tags(created) == ["winter"]


@pytest.mark.django_db
def test_create_recipe_with_a_taken_name_is_refused(user, recipe):
    """An owner cannot have two recipes of one name, and no tag is left behind."""
    with pytest.raises(DuplicateRecipeNameError, match="already have a recipe"):
        create_recipe(
            owner=user, recipe=Recipe(recipe_name="Soup", servings=2), tag_names=["orphan"]
        )
    assert Recipe.objects.filter(owner=user).count() == 1
    assert not Tag.objects.filter(tag="orphan").exists()


# --- save_metadata ---


@pytest.mark.django_db
def test_save_metadata_writes_the_fields_cuisine_and_tags(recipe):
    """Every metadata field, the cuisine and the tags are written."""
    cuisine = Cuisine.objects.create(cuisine="Thai")
    recipe.recipe_name, recipe.servings, recipe.cuisine = "Tom yum", 3, cuisine
    save_metadata(recipe=recipe, tag_names=["spicy"])
    recipe.refresh_from_db()
    assert (recipe.recipe_name, recipe.plain_name, recipe.servings) == ("Tom yum", "Tom yum", 3)
    assert recipe.cuisine == cuisine
    assert _tags(recipe) == ["spicy"]


@pytest.mark.django_db
def test_save_metadata_with_a_taken_name_writes_nothing(recipe, user, make_recipe):
    """A rename onto another of the owner's recipes is refused, tags included."""
    make_recipe(owner=user, name="Stew")
    recipe.recipe_name = "Stew"
    with pytest.raises(DuplicateRecipeNameError):
        save_metadata(recipe=recipe, tag_names=["orphan"])
    recipe.refresh_from_db()
    assert recipe.recipe_name == "Soup"
    assert _tags(recipe) == []


@pytest.mark.django_db
def test_save_metadata_of_a_deleted_recipe_raises(recipe):
    """A recipe deleted since the form opened is missing."""
    Recipe.objects.filter(pk=recipe.pk).delete()
    with pytest.raises(ObjectDoesNotExist):
        save_metadata(recipe=recipe, tag_names=[])


# --- save_field ---


@pytest.mark.django_db
def test_save_field_writes_only_that_field(recipe):
    """One field is written, its plain-text column kept current."""
    Recipe.objects.filter(pk=recipe.pk).update(servings=9)
    recipe.short_description = "<b>Hot</b> soup"
    save_field(recipe=recipe, field_name="short_description")
    recipe.refresh_from_db()
    assert recipe.plain_description == "Hot soup"
    assert recipe.servings == 9


@pytest.mark.django_db
def test_save_field_with_a_taken_name_is_refused(recipe, user, make_recipe):
    """A rename onto another of the owner's recipes is refused."""
    make_recipe(owner=user, name="Stew")
    recipe.recipe_name = "Stew"
    with pytest.raises(DuplicateRecipeNameError):
        save_field(recipe=recipe, field_name="recipe_name")


@pytest.mark.django_db
def test_save_field_of_a_deleted_recipe_raises(recipe):
    """A recipe deleted since the form opened is missing."""
    Recipe.objects.filter(pk=recipe.pk).delete()
    with pytest.raises(ObjectDoesNotExist):
        save_field(recipe=recipe, field_name="servings")
