"""Tests for the ingredient-admin forms (Plan 007)."""

import pytest

from recipes.forms.ingredient_admin_forms import IngredientForm
from recipes.models import Ingredient


@pytest.mark.django_db
def test_valid_form_saves_name_family_and_dietary_constraint(make_ingredient):
    onion = make_ingredient("onion")
    form = IngredientForm(
        data={"ingredient_name": "aubergine", "family": "VEG", "dietary_constraint": "VGN"},
        instance=onion,
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()
    assert saved.ingredient_name == "aubergine"
    assert saved.family == "VEG"
    assert saved.dietary_constraint == "VGN"


@pytest.mark.django_db
def test_rename_onto_an_existing_name_is_rejected(make_ingredient):
    onion = make_ingredient("onion")
    make_ingredient("aubergine")
    form = IngredientForm(data={"ingredient_name": "aubergine"}, instance=onion)
    assert not form.is_valid()
    assert "ingredient_name" in form.errors


@pytest.mark.django_db
def test_rename_onto_an_existing_name_is_rejected_case_insensitively(make_ingredient):
    onion = make_ingredient("onion")
    make_ingredient("Aubergine")
    form = IngredientForm(data={"ingredient_name": "aubergine"}, instance=onion)
    assert not form.is_valid()
    assert "ingredient_name" in form.errors


@pytest.mark.django_db
def test_keeping_the_current_name_is_allowed(make_ingredient):
    onion = make_ingredient("onion")
    form = IngredientForm(data={"ingredient_name": "onion", "family": "VEG"}, instance=onion)
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_recasing_an_ingredients_own_name_is_allowed(make_ingredient):
    onion = make_ingredient("onion")
    form = IngredientForm(data={"ingredient_name": "Onion"}, instance=onion)
    assert form.is_valid(), form.errors
    assert form.save().ingredient_name == "Onion"


@pytest.mark.django_db
def test_surrounding_whitespace_is_stripped(make_ingredient):
    onion = make_ingredient("onion")
    form = IngredientForm(data={"ingredient_name": "  aubergine  "}, instance=onion)
    assert form.is_valid(), form.errors
    assert form.save().ingredient_name == "aubergine"


@pytest.mark.django_db
def test_whitespace_only_name_is_rejected(make_ingredient):
    onion = make_ingredient("onion")
    form = IngredientForm(data={"ingredient_name": "   "}, instance=onion)
    assert not form.is_valid()
    assert "ingredient_name" in form.errors


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["family", "dietary_constraint"])
def test_unknown_choice_is_rejected(make_ingredient, field):
    onion = make_ingredient("onion")
    form = IngredientForm(data={"ingredient_name": "onion", field: "NOPE"}, instance=onion)
    assert not form.is_valid()
    assert field in form.errors


@pytest.mark.django_db
def test_family_and_dietary_constraint_may_be_blank(make_ingredient):
    onion = make_ingredient("onion")
    form = IngredientForm(
        data={"ingredient_name": "onion", "family": "", "dietary_constraint": ""}, instance=onion
    )
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_rejected_rename_does_not_write(make_ingredient):
    onion = make_ingredient("onion")
    make_ingredient("aubergine")
    IngredientForm(data={"ingredient_name": "aubergine"}, instance=onion).is_valid()
    assert Ingredient.objects.get(pk=onion.pk).ingredient_name == "onion"
