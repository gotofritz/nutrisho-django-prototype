"""Tests for recipe scale (multiply servings + quantities) view."""

from decimal import Decimal

import pytest
from django.test import Client

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe


@pytest.fixture
def auth_client(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def recipe(user, db):
    return Recipe.objects.create(recipe_name="Scale Recipe", owner=user, servings=4)


@pytest.fixture
def recipe_no_servings(user, db):
    return Recipe.objects.create(recipe_name="Scale No Servings", owner=user, servings=None)


@pytest.fixture
def group(recipe):
    return IngredientGroup.objects.create(recipe=recipe, group_name="Main", index_in_sequence=0)


@pytest.fixture
def group_no_servings(recipe_no_servings):
    return IngredientGroup.objects.create(
        recipe=recipe_no_servings, group_name="Main", index_in_sequence=0
    )


@pytest.fixture
def iir(group):
    ing = Ingredient.objects.create(ingredient_name="onion-scale")
    return IngredientInRecipe.objects.create(
        ingredient=ing,
        ingredient_group=group,
        index_in_sequence=0,
        quantity=Decimal("2.00"),
    )


@pytest.fixture
def iir_null_quantity(group):
    ing = Ingredient.objects.create(ingredient_name="salt-scale")
    return IngredientInRecipe.objects.create(
        ingredient=ing,
        ingredient_group=group,
        index_in_sequence=1,
        quantity=None,
    )


# --- Scale view ---


@pytest.mark.django_db
def test_scale_get_not_allowed(auth_client, recipe):
    response = auth_client.get(f"/recipes/{recipe.pk}/scale/")
    assert response.status_code == 405


@pytest.mark.django_db
def test_scale_post_updates_servings(auth_client, recipe, group, iir):
    # multiplier=2, old_serves=4 → round(4*2)=8
    auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "2"})
    recipe.refresh_from_db()
    assert recipe.servings == 8


@pytest.mark.django_db
def test_scale_post_multiplies_quantities(auth_client, recipe, group, iir):
    # multiplier=2, quantity=2.00 → 4.00
    auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "2"})
    iir.refresh_from_db()
    assert iir.quantity == Decimal("4.00")


@pytest.mark.django_db
def test_scale_post_fractional_multiplier(auth_client, recipe, group):
    # user example: serves=4, 200g bread, multiplier=3.2 → serves=13, 640g
    ing = Ingredient.objects.create(ingredient_name="bread-scale")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=0, quantity=Decimal("200.00")
    )
    auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "3.2"})
    recipe.refresh_from_db()
    iir.refresh_from_db()
    assert recipe.servings == 13  # round(4 * 3.2) = round(12.8) = 13
    assert iir.quantity == Decimal("640.00")  # 200 * 3.2 exact


@pytest.mark.django_db
def test_scale_post_skips_null_quantities(auth_client, recipe, group, iir_null_quantity):
    auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "2"})
    iir_null_quantity.refresh_from_db()
    assert iir_null_quantity.quantity is None


@pytest.mark.django_db
def test_scale_post_null_servings_scales_quantities_but_leaves_servings_none(
    auth_client, recipe_no_servings, group_no_servings
):
    ing = Ingredient.objects.create(ingredient_name="garlic-scale")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing,
        ingredient_group=group_no_servings,
        index_in_sequence=0,
        quantity=Decimal("3.00"),
    )
    auth_client.post(f"/recipes/{recipe_no_servings.pk}/scale/", {"multiplier": "3"})
    iir.refresh_from_db()
    recipe_no_servings.refresh_from_db()
    assert iir.quantity == Decimal("9.00")
    assert recipe_no_servings.servings is None


@pytest.mark.django_db
def test_scale_post_null_servings_extreme_multiplier_returns_400(
    auth_client, recipe_no_servings, group_no_servings
):
    """Extreme multiplier must return 400, not 500 from InvalidOperation in quantize."""
    ing = Ingredient.objects.create(ingredient_name="extreme-scale")
    IngredientInRecipe.objects.create(
        ingredient=ing,
        ingredient_group=group_no_servings,
        index_in_sequence=0,
        quantity=Decimal("99999.99"),
    )
    response = auth_client.post(f"/recipes/{recipe_no_servings.pk}/scale/", {"multiplier": "1E+50"})
    assert response.status_code == 422


@pytest.mark.django_db
def test_scale_post_htmx_returns_hx_redirect(auth_client, recipe, group, iir):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/scale/",
        {"multiplier": "2"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert "HX-Redirect" in response


@pytest.mark.django_db
def test_scale_post_non_htmx_redirects(auth_client, recipe, group, iir):
    response = auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "2"})
    assert response.status_code == 302


@pytest.mark.django_db
def test_scale_post_invalid_multiplier_returns_422(auth_client, recipe):
    response = auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "abc"})
    assert response.status_code == 422
    assert "form-error" in response.content.decode()


@pytest.mark.django_db
def test_scale_post_zero_multiplier_returns_422(auth_client, recipe):
    response = auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "0"})
    assert response.status_code == 422


@pytest.mark.django_db
def test_scale_post_negative_multiplier_returns_422(auth_client, recipe):
    response = auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "-1"})
    assert response.status_code == 422


@pytest.mark.django_db
def test_scale_panel_htmx_get_returns_partial(auth_client, recipe):
    response = auth_client.get(
        f"/recipes/{recipe.pk}/scale/panel/",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert "recipes/partials/_scale_panel.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_scale_down_clamps_servings_to_minimum_1(auth_client, user):
    """Halving a 1-serving recipe must not round servings down to 0."""
    r = Recipe.objects.create(recipe_name="Tiny Scale", owner=user, servings=1)
    response = auth_client.post(f"/recipes/{r.pk}/scale/", {"multiplier": "0.5"})
    assert response.status_code == 302
    r.refresh_from_db()
    assert r.servings == 1


@pytest.mark.django_db
def test_scale_down_sub_half_result_clamps_to_1(auth_client, recipe, group, iir):
    """servings=4, multiplier=0.1 → round(0.4)=0 → clamped to 1; quantities still scale."""
    response = auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "0.1"})
    assert response.status_code == 302
    recipe.refresh_from_db()
    iir.refresh_from_db()
    assert recipe.servings == 1
    assert iir.quantity == Decimal("0.20")


@pytest.mark.django_db
def test_scale_servings_overflow_returns_422(auth_client, recipe, group, iir):
    """servings=4 x 10000 = 40000 exceeds PositiveSmallIntegerField; reject, change nothing."""
    response = auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "10000"})
    assert response.status_code == 422
    recipe.refresh_from_db()
    iir.refresh_from_db()
    assert recipe.servings == 4
    assert iir.quantity == Decimal("2.00")


@pytest.mark.django_db
def test_scale_quantity_overflow_returns_422(auth_client, recipe, group):
    """Scaled quantity exceeding DecimalField(max_digits=7, dp=2) rejects whole scale."""
    ing = Ingredient.objects.create(ingredient_name="bulk-flour")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=0, quantity=Decimal("99999.00")
    )
    # servings 4 * 1.5 = 6 fits; quantity 99999 * 1.5 = 149998.50 overflows
    response = auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "1.5"})
    assert response.status_code == 422
    recipe.refresh_from_db()
    iir.refresh_from_db()
    assert recipe.servings == 4
    assert iir.quantity == Decimal("99999.00")


@pytest.mark.django_db
def test_scale_acquires_row_lock(auth_client, recipe, group, iir):
    """recipe_scale must call select_for_update() to prevent concurrent-scale data races."""
    from unittest.mock import patch

    from django.db.models import QuerySet

    locked_models: list[str] = []
    original_sfu = QuerySet.select_for_update

    def spy_sfu(self, *args, **kwargs):
        locked_models.append(self.model.__name__)
        return original_sfu(self, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", spy_sfu):
        auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "2"})

    assert locked_models, "select_for_update() was not called; concurrent scales will race"


@pytest.mark.django_db
def test_scale_servings_exact_half_rounds_up(auth_client, user):
    """5 * 0.5 = 2.5 → 3 with ROUND_HALF_UP, not 2 with banker's rounding."""
    r = Recipe.objects.create(recipe_name="Half Scale", owner=user, servings=5)
    auth_client.post(f"/recipes/{r.pk}/scale/", {"multiplier": "0.5"})
    r.refresh_from_db()
    assert r.servings == 3


@pytest.mark.django_db
def test_scale_quantity_exact_half_rounds_up(auth_client, recipe, group):
    """0.05 * 0.5 = 0.025 → 0.03 with ROUND_HALF_UP, not 0.02 with banker's rounding."""
    ing = Ingredient.objects.create(ingredient_name="half-rounding")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=0, quantity=Decimal("0.05")
    )
    auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "0.5"})
    iir.refresh_from_db()
    assert iir.quantity == Decimal("0.03")


@pytest.mark.django_db
def test_scale_servings_extreme_multiplier_returns_422(auth_client, recipe, group, iir):
    """Extreme multiplier with non-null servings must return 422, not 500 from InvalidOperation."""
    response = auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "1E+50"})
    assert response.status_code == 422
    recipe.refresh_from_db()
    assert recipe.servings == 4  # unchanged
