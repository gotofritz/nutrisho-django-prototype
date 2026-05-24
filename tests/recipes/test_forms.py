"""Tests for RecipeEditForm and helpers."""

import pytest

from recipes.forms.recipe_edit_form import (
    MIN_NUMBER_STEP_FIELDS,
    RecipeEditForm,
    _textarea_height,
)
from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", 54),
        ("short", 54),
        ("x" * 64, 54),  # exactly 1 line
        ("x" * 128, 54),  # 2 lines — still min
        ("x" * 192, 84),  # 3 lines → min + 1 extra line
        ("x" * 256, 114),  # 4 lines → min + 2 extra lines
    ],
)
def test_textarea_height(text, expected):
    assert _textarea_height(text) == expected


@pytest.mark.django_db
def test_form_init_no_steps_creates_blank_step_fields(user):
    recipe = Recipe.objects.create(recipe_name="Empty", owner=user)
    form = RecipeEditForm({"recipe_name": "Empty", "short_description": ""}, instance=recipe)
    step_fields = list(form.get_step_fields())
    assert len(step_fields) == MIN_NUMBER_STEP_FIELDS


@pytest.mark.django_db
def test_form_init_with_steps_includes_existing(user):
    recipe = Recipe.objects.create(recipe_name="With Steps", owner=user)
    Step.objects.create(recipe=recipe, step_text="Boil water", index_in_sequence=0)
    Step.objects.create(recipe=recipe, step_text="Add pasta", index_in_sequence=1)
    form = RecipeEditForm({"recipe_name": "With Steps", "short_description": ""}, instance=recipe)
    step_fields = list(form.get_step_fields())
    assert len(step_fields) >= MIN_NUMBER_STEP_FIELDS


@pytest.mark.django_db
def test_form_get_step_fields_yields_correct_names(user):
    recipe = Recipe.objects.create(recipe_name="Steps", owner=user)
    Step.objects.create(recipe=recipe, step_text="Step one", index_in_sequence=0)
    form = RecipeEditForm({"recipe_name": "Steps", "short_description": ""}, instance=recipe)
    names = [f.name for f in form.get_step_fields()]
    assert all(n.startswith("step-") for n in names)


@pytest.mark.django_db
def test_form_get_groups_empty_recipe(user):
    recipe = Recipe.objects.create(recipe_name="No groups", owner=user)
    form = RecipeEditForm({"recipe_name": "No groups", "short_description": ""}, instance=recipe)
    groups = list(form.get_groups())
    assert groups == []


@pytest.mark.django_db
def test_form_is_valid_minimal(user):
    recipe = Recipe.objects.create(recipe_name="Valid", owner=user)
    form = RecipeEditForm({"recipe_name": "Valid", "short_description": ""}, instance=recipe)
    assert form.is_valid()


@pytest.fixture
def recipe_with_ingredients(user, db):
    recipe = Recipe.objects.create(recipe_name="Full Recipe", owner=user)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="Main", index_in_sequence=0)
    ing = Ingredient.objects.create(ingredient_name="onion")
    IngredientInRecipe.objects.create(
        ingredient=ing,
        ingredient_group=group,
        index_in_sequence=0,
        quantity=2,
        unit="pcs",
        preparation="diced",
    )
    return recipe


@pytest.mark.django_db
def test_form_init_with_ingredients_creates_group_fields(recipe_with_ingredients):
    form = RecipeEditForm(
        {"recipe_name": "Full Recipe", "short_description": ""},
        instance=recipe_with_ingredients,
    )
    field_names = list(form.fields.keys())
    assert any(n.startswith("group-") for n in field_names)
    assert any("quantity" in n for n in field_names)
    assert any("unit" in n for n in field_names)
    assert any("name" in n for n in field_names)
    assert any("preparation" in n for n in field_names)


@pytest.mark.django_db
def test_form_get_groups_with_ingredients_yields_fields(recipe_with_ingredients):
    form = RecipeEditForm(
        {"recipe_name": "Full Recipe", "short_description": ""},
        instance=recipe_with_ingredients,
    )
    groups = list(form.get_groups())
    assert len(groups) > 0
    field, is_group, is_first, is_last = groups[0]
    assert field is not None


@pytest.mark.django_db
def test_form_get_groups_flags_group_header(recipe_with_ingredients):
    form = RecipeEditForm(
        {"recipe_name": "Full Recipe", "short_description": ""},
        instance=recipe_with_ingredients,
    )
    group_headers = [(f, g, fst, lst) for f, g, fst, lst in form.get_groups() if g]
    assert len(group_headers) == 1  # one group header
