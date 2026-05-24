"""Tests for RecipeEditForm and helpers."""

import pytest

from recipes.forms.recipe_edit_form import (
    MIN_NUMBER_STEP_FIELDS,
    RecipeEditForm,
    _textarea_height,
)
from recipes.models import Recipe, Step


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
    # 2 existing + EXTRA_BLANK_STEP_FIELDS blank, min MIN_NUMBER_STEP_FIELDS total
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
