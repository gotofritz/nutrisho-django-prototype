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


def _iir(quantity: Decimal | None, unit: str = "") -> IngredientInRecipe:
    """An unsaved IIR carrying just what the display filter reads."""
    return IngredientInRecipe(
        ingredient=Ingredient(ingredient_name="onion"), quantity=quantity, unit=unit
    )


def test_display_ingredient_name_pluralises_above_one():
    from recipes.templatetags.recipe_filters import display_ingredient_name

    assert display_ingredient_name(_iir(Decimal("2"))) == "onions"


def test_display_ingredient_name_pluralises_below_one():
    """0.5 is not 1, so it reads as a plural — 'half onions', not 'half onion'."""
    from recipes.templatetags.recipe_filters import display_ingredient_name

    assert display_ingredient_name(_iir(Decimal("0.5"))) == "onions"


def test_display_ingredient_name_keeps_the_singular_at_exactly_one():
    from recipes.templatetags.recipe_filters import display_ingredient_name

    assert display_ingredient_name(_iir(Decimal("1"))) == "onion"
    # value comparison, not string: 1.00 is still one
    assert display_ingredient_name(_iir(Decimal("1.00"))) == "onion"


def test_display_ingredient_name_keeps_the_singular_with_a_unit():
    """The unit check is what keeps mass nouns safe: 200 g onion, never onions."""
    from recipes.templatetags.recipe_filters import display_ingredient_name

    assert display_ingredient_name(_iir(Decimal("200"), unit="g")) == "onion"


def test_display_ingredient_name_keeps_the_singular_without_a_quantity():
    from recipes.templatetags.recipe_filters import display_ingredient_name

    assert display_ingredient_name(_iir(None)) == "onion"


def test_display_ingredient_name_honours_the_plural_name_override():
    from recipes.templatetags.recipe_filters import display_ingredient_name

    iir = IngredientInRecipe(
        ingredient=Ingredient(ingredient_name="broccoli", plural_name="broccoli"),
        quantity=Decimal("3"),
        unit="",
    )
    assert display_ingredient_name(iir) == "broccoli"


@pytest.mark.django_db
def test_recipe_detail_pluralises_a_countable_ingredient(client: Client, user):
    """recipe_scale persists the scaled quantity, so 2 must render as "2 onions"."""
    recipe = Recipe.objects.create(recipe_name="Plural Test", owner=user, servings=4)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="", index_in_sequence=1)
    onion = Ingredient.objects.create(ingredient_name="onion")
    IngredientInRecipe.objects.create(
        ingredient=onion, ingredient_group=group, index_in_sequence=1, quantity=Decimal("2")
    )

    client.force_login(user)
    content = client.get(recipe.get_absolute_url()).content.decode()
    assert '<span class="ingredient-name">onions</span>' in content


@pytest.mark.django_db
def test_recipe_detail_keeps_the_singular_at_one_and_with_a_unit(client: Client, user):
    recipe = Recipe.objects.create(recipe_name="Singular Test", owner=user, servings=4)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="", index_in_sequence=1)
    onion = Ingredient.objects.create(ingredient_name="onion")
    garlic = Ingredient.objects.create(ingredient_name="garlic")
    IngredientInRecipe.objects.create(
        ingredient=onion, ingredient_group=group, index_in_sequence=1, quantity=Decimal("1")
    )
    IngredientInRecipe.objects.create(
        ingredient=garlic,
        ingredient_group=group,
        index_in_sequence=2,
        quantity=Decimal("200"),
        unit="g",
    )

    client.force_login(user)
    content = client.get(recipe.get_absolute_url()).content.decode()
    assert '<span class="ingredient-name">onion</span>' in content
    assert '<span class="ingredient-name">garlic</span>' in content
    assert "garlics" not in content


def test_display_ingredient_name_is_blank_for_a_missing_row():
    """A mistyped template variable resolves to "", not an IIR — don't crash the page."""
    from recipes.templatetags.recipe_filters import display_ingredient_name

    assert display_ingredient_name("") == ""
