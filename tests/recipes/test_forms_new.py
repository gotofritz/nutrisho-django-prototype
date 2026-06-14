"""Tests for new focused forms (Plan 004, Step 3)."""

import pytest

from recipes.forms.field_forms import EDITABLE_RECIPE_FIELDS, RecipeFieldForm, RecipeMetadataForm
from recipes.forms.ingredient_forms import IngredientGroupForm, IngredientInRecipeForm
from recipes.forms.step_form import StepForm
from recipes.models import Recipe


@pytest.mark.django_db
def test_recipe_field_form_recipe_name_max_length(user):
    recipe = Recipe.objects.create(recipe_name="Test", owner=user)
    form = RecipeFieldForm("recipe_name", data={"recipe_name": "x" * 201}, instance=recipe)
    assert not form.is_valid()
    assert "recipe_name" in form.errors


@pytest.mark.django_db
def test_recipe_field_form_only_contains_requested_field(user):
    recipe = Recipe.objects.create(recipe_name="Test", owner=user)
    form = RecipeFieldForm("recipe_name", data={"recipe_name": "Test"}, instance=recipe)
    assert list(form.fields.keys()) == ["recipe_name"]


@pytest.mark.django_db
def test_recipe_field_form_rejects_unknown_field(user):
    recipe = Recipe.objects.create(recipe_name="Test", owner=user)
    with pytest.raises(ValueError):
        RecipeFieldForm("nonexistent_field", data={}, instance=recipe)


@pytest.mark.django_db
def test_recipe_field_form_valid_save(user):
    recipe = Recipe.objects.create(recipe_name="Old Name", owner=user)
    form = RecipeFieldForm("recipe_name", data={"recipe_name": "New Name"}, instance=recipe)
    assert form.is_valid()
    form.save()
    recipe.refresh_from_db()
    assert recipe.recipe_name == "New Name"


@pytest.mark.django_db
def test_recipe_field_form_all_editable_fields_accepted(user):
    for field in EDITABLE_RECIPE_FIELDS:
        recipe = Recipe.objects.create(recipe_name=f"Recipe-{field}", owner=user)
        form = RecipeFieldForm(field, instance=recipe)
        assert field in form.fields


def test_step_form_rejects_empty_step_text():
    form = StepForm(data={"step_text": ""})
    assert not form.is_valid()
    assert "step_text" in form.errors


def test_step_form_accepts_valid_step():
    form = StepForm(data={"step_text": "Boil water for 10 minutes"})
    assert form.is_valid()


def test_ingredient_form_accepts_valid_decimal_quantity():
    form = IngredientInRecipeForm(
        data={
            "ingredient_name": "salt",
            "quantity": "2.50",
            "unit": "cups",
            "preparation": "",
            "note": "",
        }
    )
    assert form.is_valid()


def test_ingredient_form_rejects_negative_quantity():
    form = IngredientInRecipeForm(
        data={"quantity": "-1", "unit": "cups", "preparation": "", "note": ""}
    )
    assert not form.is_valid()
    assert "quantity" in form.errors


def test_ingredient_group_form_accepts_blank_group_name():
    form = IngredientGroupForm(data={"group_name": ""})
    assert form.is_valid()


def test_ingredient_group_form_accepts_named_group():
    form = IngredientGroupForm(data={"group_name": "Sauce"})
    assert form.is_valid()


@pytest.mark.django_db
def test_ingredient_in_recipe_form_commit_false_does_not_create_ingredient(db):
    """save(commit=False) must not write Ingredient to DB — side-effect free."""
    from recipes.models import Ingredient

    form = IngredientInRecipeForm(
        data={"ingredient_name": "ghost-veggie", "quantity": "", "unit": "", "preparation": "", "note": ""}
    )
    assert form.is_valid()
    form.save(commit=False)
    assert not Ingredient.objects.filter(ingredient_name="ghost-veggie").exists()


@pytest.mark.django_db
def test_recipe_metadata_form_commit_false_does_not_create_cuisine(user):
    """save(commit=False) must not write Cuisine to DB — side-effect free."""
    from recipes.models import Cuisine

    recipe = Recipe.objects.create(recipe_name="Test", owner=user)
    form = RecipeMetadataForm(
        data={
            "recipe_name": "Test",
            "short_description": "",
            "servings": "",
            "source_instance": "",
            "cuisine_name": "ghost-cuisine",
        },
        instance=recipe,
    )
    assert form.is_valid()
    form.save(commit=False)
    assert not Cuisine.objects.filter(cuisine="ghost-cuisine").exists()


@pytest.mark.django_db
def test_recipe_metadata_form_commit_false_clears_cuisine_when_blank(user):
    """save(commit=False) with blank cuisine_name must set recipe.cuisine = None in-memory."""
    from recipes.models import Cuisine

    cuisine = Cuisine.objects.create(cuisine="Italian")
    recipe = Recipe.objects.create(recipe_name="Test", owner=user, cuisine=cuisine)
    form = RecipeMetadataForm(
        data={
            "recipe_name": "Test",
            "short_description": "",
            "servings": "",
            "source_instance": "",
            "cuisine_name": "",
        },
        instance=recipe,
    )
    assert form.is_valid()
    result = form.save(commit=False)
    assert result.cuisine is None


@pytest.mark.django_db
def test_recipe_metadata_form_commit_false_sets_existing_cuisine(user):
    """save(commit=False) with existing cuisine must set recipe.cuisine in-memory without write."""
    from recipes.models import Cuisine

    cuisine = Cuisine.objects.create(cuisine="Thai")
    recipe = Recipe.objects.create(recipe_name="Test", owner=user)
    form = RecipeMetadataForm(
        data={
            "recipe_name": "Test",
            "short_description": "",
            "servings": "",
            "source_instance": "",
            "cuisine_name": "Thai",
        },
        instance=recipe,
    )
    assert form.is_valid()
    result = form.save(commit=False)
    assert result.cuisine == cuisine


@pytest.mark.django_db
def test_ingredient_form_commit_false_sets_existing_ingredient(user):
    """save(commit=False) with existing ingredient must set iir.ingredient in-memory."""
    from recipes.models import Ingredient

    ing = Ingredient.objects.create(ingredient_name="basil")
    form = IngredientInRecipeForm(
        data={"ingredient_name": "basil", "quantity": "", "unit": "", "preparation": "", "note": ""}
    )
    assert form.is_valid()
    iir = form.save(commit=False)
    assert iir.ingredient == ing
