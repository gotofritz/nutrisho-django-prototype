"""Tests for recipe_filters template tags."""

from decimal import Decimal

import pytest
from django.test import Client

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step


def test_format_quantity_strips_trailing_zeros():
    from decimal import Decimal

    from recipes.templatetags.recipe_filters import format_quantity

    assert format_quantity(Decimal("4.00")) == "4"
    assert format_quantity(Decimal("2.50")) == "2.5"
    assert format_quantity(Decimal("2.55")) == "2.55"
    assert format_quantity(Decimal("0.50")) == "0.5"
    assert format_quantity(Decimal("100.00")) == "100"
    assert format_quantity(None) == ""


def test_scale_filter_removed():
    """scale filter must not exist — quantity is full-recipe amount, not per-serving."""
    from recipes.templatetags import recipe_filters

    assert not hasattr(recipe_filters, "scale")


@pytest.mark.django_db
def test_recipe_detail_renders_raw_quantities(client: Client, user):
    """Recipe detail page renders raw (unscaled) quantities until data is migrated."""
    recipe = Recipe.objects.create(recipe_name="Scale Test", owner=user, servings=4)
    Step.objects.create(recipe=recipe, step_text="Mix", index_in_sequence=1)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="", index_in_sequence=1)
    ing = Ingredient.objects.create(ingredient_name="flour")
    IngredientInRecipe.objects.create(
        ingredient=ing,
        ingredient_group=group,
        index_in_sequence=1,
        quantity=Decimal("2.50"),
        unit="cups",
        preparation="",
    )

    client.force_login(user)
    response = client.get(recipe.get_absolute_url())
    assert response.status_code == 200
    content = response.content.decode()
    assert "ingredient-quantity" in content
    # raw quantity rendered; scaling not applied until data is migrated
    assert '<span class="ingredient-quantity">2.5<' in content
