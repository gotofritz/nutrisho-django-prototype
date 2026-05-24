"""Tests for recipes models."""

import pytest

from recipes.models import (
    Cuisine,
    Ingredient,
    IngredientGroup,
    IngredientInRecipe,
    Recipe,
    Source,
    Step,
    Tag,
)


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


@pytest.mark.django_db
def test_cuisine_natural_key():
    c = Cuisine.objects.create(cuisine="Italian")
    assert c.natural_key() == "Italian"


@pytest.mark.django_db
def test_source_natural_key():
    s = Source.objects.create(short_name="Moro", source="ISBN-123")
    assert s.natural_key() == "Moro"


@pytest.mark.django_db
def test_tag_natural_key(user):
    recipe = Recipe.objects.create(recipe_name="Tagged", owner=user)
    t = Tag.objects.create(tag="vegan")
    t.recipe.add(recipe)
    assert t.natural_key() == "vegan"


@pytest.mark.django_db
def test_ingredient_natural_key():
    ing = Ingredient.objects.create(ingredient_name="salt")
    assert ing.natural_key() == "salt"


@pytest.mark.django_db
def test_ingredient_group_natural_key(user):
    recipe = Recipe.objects.create(recipe_name="R", owner=user)
    g = IngredientGroup.objects.create(recipe=recipe, group_name="Main", index_in_sequence=0)
    assert g.natural_key() == "Main"


@pytest.mark.django_db
def test_step_natural_key(user):
    recipe = Recipe.objects.create(recipe_name="R", owner=user)
    step = Step.objects.create(recipe=recipe, step_text="Chop", index_in_sequence=0)
    assert step.natural_key() == (0, "Chop")


@pytest.mark.django_db
def test_ingredient_in_recipe_natural_key(user):
    recipe = Recipe.objects.create(recipe_name="R", owner=user)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="G", index_in_sequence=0)
    ing = Ingredient.objects.create(ingredient_name="onion")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=0, quantity=2
    )
    key = iir.natural_key()
    assert key[3] == "onion"
