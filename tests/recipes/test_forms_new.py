"""Tests for new focused forms (Plan 004, Step 3)."""

import pytest

from recipes.forms.field_forms import EDITABLE_RECIPE_FIELDS, RecipeFieldForm
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
        data={"quantity": "2.50", "unit": "cups", "preparation": "", "note": ""}
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
