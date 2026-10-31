"""Tests for scaling a recipe: display-time `?servings=N` and "Save as scaled copy" (#36)."""

from decimal import Decimal

import pytest
from django.test import Client

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe


@pytest.fixture
def auth_client(user):
    """Auth client."""
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def recipe(user, db):
    """Recipe."""
    return Recipe.objects.create(recipe_name="Scale Recipe", owner=user, servings=4)


@pytest.fixture
def group(recipe):
    """Group."""
    return IngredientGroup.objects.create(recipe=recipe, group_name="Main", index_in_sequence=0)


@pytest.fixture
def make_iir(group):
    """Add an ingredient row to the recipe's group."""

    def _make(name: str, quantity: Decimal | None, unit: str = "") -> IngredientInRecipe:
        return IngredientInRecipe.objects.create(
            ingredient=Ingredient.objects.create(ingredient_name=name),
            ingredient_group=group,
            index_in_sequence=IngredientInRecipe.objects.filter(ingredient_group=group).count(),
            quantity=quantity,
            unit=unit,
        )

    return _make


@pytest.fixture
def iir(make_iir):
    """2 g flour, for a 4-serving recipe."""
    return make_iir("flour-scale", Decimal("2.00"), unit="g")


def _quantity_span(value: str) -> str:
    return f'<span class="ingredient-quantity">{value}</span>'


# --- Display-time scaling: GET /recipes/<id>/?servings=N ---


@pytest.mark.django_db
def test_recipe_page_shows_stored_quantities_without_servings(auth_client, recipe, iir):
    """No ?servings: the stored quantities, as before."""
    content = auth_client.get(f"/recipes/{recipe.pk}/").content.decode()
    assert _quantity_span("2") in content
    assert "scaled-note" not in content


@pytest.mark.django_db
def test_recipe_page_scales_quantities_to_target_servings(auth_client, recipe, iir):
    """2 g for 4 servings is 3 g for 6."""
    response = auth_client.get(f"/recipes/{recipe.pk}/?servings=6")
    assert response.status_code == 200
    content = response.content.decode()
    assert _quantity_span("3") in content
    assert "Serves 6" in content


@pytest.mark.django_db
def test_recipe_page_scaling_writes_nothing(auth_client, recipe, iir):
    """Scaling is presentation: servings and quantities in the database are untouched."""
    auth_client.get(f"/recipes/{recipe.pk}/?servings=6")
    recipe.refresh_from_db()
    iir.refresh_from_db()
    assert recipe.servings == 4
    assert iir.quantity == Decimal("2.00")


@pytest.mark.django_db
def test_recipe_page_scaled_view_says_it_is_temporary_and_offers_reset(auth_client, recipe, iir):
    """The scaled view names the stored count and links back to the unscaled page."""
    content = auth_client.get(f"/recipes/{recipe.pk}/?servings=6").content.decode()
    assert "scaled-note" in content
    assert "scaled from 4" in content
    assert f'href="/recipes/{recipe.pk}/"' in content
    assert "Reset" in content


@pytest.mark.django_db
def test_recipe_page_scaled_ingredients_are_read_only(auth_client, recipe, iir):
    """Editing a scaled quantity would save the wrong number, so no edit triggers."""
    content = auth_client.get(f"/recipes/{recipe.pk}/?servings=6").content.decode()
    assert f"/recipes/{recipe.pk}/ingredients/{iir.pk}/edit/" not in content
    assert "/field/servings/edit/" not in content
    assert 'class="ingredient-select"' not in content


@pytest.mark.django_db
def test_recipe_page_small_quantities_are_not_lost(auth_client, recipe, make_iir):
    """0.01 at 4 servings is 0.0025 at 1 serving, not 0."""
    make_iir("saffron-scale", Decimal("0.01"), unit="g")
    content = auth_client.get(f"/recipes/{recipe.pk}/?servings=1").content.decode()
    assert _quantity_span("0.0025") in content


@pytest.mark.django_db
def test_recipe_page_scaled_quantities_do_not_drift(auth_client, recipe, make_iir):
    """Every view is computed from the stored value: 1 for 4 is 0.75 for 3, 1 for 4 again."""
    make_iir("lemon-scale", Decimal("1"), unit="tbsp")
    assert _quantity_span("0.75") in (
        auth_client.get(f"/recipes/{recipe.pk}/?servings=3").content.decode()
    )
    assert _quantity_span("1") in (
        auth_client.get(f"/recipes/{recipe.pk}/?servings=4").content.decode()
    )


@pytest.mark.django_db
def test_recipe_page_rounds_to_two_decimals(auth_client, recipe, make_iir):
    """1 tsp for 3 servings is 0.33 tsp for 1."""
    recipe.servings = 3
    recipe.save()
    make_iir("cumin-scale", Decimal("1"), unit="tsp")
    content = auth_client.get(f"/recipes/{recipe.pk}/?servings=1").content.decode()
    assert _quantity_span("0.33") in content


@pytest.mark.django_db
def test_recipe_page_pluralises_on_the_scaled_quantity(auth_client, recipe, make_iir):
    """1 onion for 4 servings reads "2 onions" for 8, and 2 onions read "1 onion" for 2."""
    make_iir("onion", Decimal("1"))
    make_iir("leek", Decimal("2"))
    doubled = auth_client.get(f"/recipes/{recipe.pk}/?servings=8").content.decode()
    assert '<span class="ingredient-name">onions</span>' in doubled
    halved = auth_client.get(f"/recipes/{recipe.pk}/?servings=2").content.decode()
    assert '<span class="ingredient-name">leek</span>' in halved


@pytest.mark.django_db
def test_recipe_page_leaves_missing_quantities_blank(auth_client, recipe, make_iir):
    """An ingredient with no quantity ("salt, to taste") has nothing to scale."""
    make_iir("salt-scale", None)
    content = auth_client.get(f"/recipes/{recipe.pk}/?servings=8").content.decode()
    assert _quantity_span("") in content


@pytest.mark.django_db
def test_recipe_page_at_stored_servings_is_the_normal_page(auth_client, recipe, iir):
    """?servings equal to the stored count is not scaling: the editable page."""
    content = auth_client.get(f"/recipes/{recipe.pk}/?servings=4").content.decode()
    assert "scaled-note" not in content
    assert f"/recipes/{recipe.pk}/ingredients/{iir.pk}/edit/" in content


@pytest.mark.parametrize("raw", ["abc", "0", "-1", "1.5", "99999", ""])
@pytest.mark.django_db
def test_recipe_page_ignores_invalid_servings(auth_client, recipe, iir, raw):
    """A bad ?servings shows the recipe as stored rather than erroring."""
    response = auth_client.get(f"/recipes/{recipe.pk}/?servings={raw}")
    assert response.status_code == 200
    content = response.content.decode()
    assert _quantity_span("2") in content
    assert "scaled-note" not in content


@pytest.mark.django_db
def test_recipe_page_htmx_scaled_returns_partial(auth_client, recipe, iir):
    """Boosted navigation to a scaled URL swaps in the scaled content partial."""
    response = auth_client.get(
        f"/recipes/{recipe.pk}/?servings=6", HTTP_HX_REQUEST="true", HTTP_HX_BOOSTED="true"
    )
    assert "recipes/partials/_recipe_content.html" in [t.name for t in response.templates]
    assert _quantity_span("3") in response.content.decode()


# --- Scale panel ---


@pytest.mark.django_db
def test_scale_panel_htmx_get_returns_partial(auth_client, recipe):
    """Scale panel htmx get returns partial."""
    response = auth_client.get(f"/recipes/{recipe.pk}/scale/panel/", HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert "recipes/partials/_scale_panel.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_scale_panel_asks_for_servings_and_shows_the_page(auth_client, recipe):
    """The panel asks for a serving count and GETs the recipe page with it."""
    content = auth_client.get(
        f"/recipes/{recipe.pk}/scale/panel/", HTTP_HX_REQUEST="true"
    ).content.decode()
    assert 'method="get"' in content
    assert f'action="/recipes/{recipe.pk}/"' in content
    assert 'name="servings"' in content
    assert 'value="4"' in content
    assert "multiplier" not in content


@pytest.mark.django_db
def test_scale_panel_prefills_the_current_target(auth_client, recipe):
    """Opened from a scaled page, the panel starts at that page's serving count."""
    content = auth_client.get(
        f"/recipes/{recipe.pk}/scale/panel/?servings=6", HTTP_HX_REQUEST="true"
    ).content.decode()
    assert 'value="6"' in content


@pytest.mark.django_db
def test_scaled_page_scale_button_carries_the_target(auth_client, recipe):
    """The nav scale button reopens the panel at the shown serving count."""
    content = auth_client.get(f"/recipes/{recipe.pk}/?servings=6").content.decode()
    assert f"/recipes/{recipe.pk}/scale/panel/?servings=6" in content


# --- The in-place multiplier is gone ---


@pytest.mark.django_db
def test_in_place_scale_endpoint_is_gone(auth_client, recipe, iir):
    """POST /scale/ used to rewrite quantities; it must no longer exist."""
    response = auth_client.post(f"/recipes/{recipe.pk}/scale/", {"multiplier": "2"})
    assert response.status_code == 404
    iir.refresh_from_db()
    assert iir.quantity == Decimal("2.00")


# --- Save as scaled copy: POST /recipes/<id>/scale/copy/ ---


def _copy(auth_client, recipe, servings: str, **headers):
    return auth_client.post(f"/recipes/{recipe.pk}/scale/copy/", {"servings": servings}, **headers)


@pytest.mark.django_db
def test_scale_copy_get_not_allowed(auth_client, recipe):
    """Scale copy is POST only."""
    response = auth_client.get(f"/recipes/{recipe.pk}/scale/copy/")
    assert response.status_code == 405


@pytest.mark.django_db
def test_scale_copy_creates_a_scaled_copy(auth_client, recipe, iir):
    """The copy stores the target servings and quantities scaled to match."""
    _copy(auth_client, recipe, "6")
    copy = Recipe.objects.exclude(pk=recipe.pk).get()
    assert copy.servings == 6
    copied = IngredientInRecipe.objects.get(ingredient_group__recipe=copy)
    assert copied.quantity == Decimal("3.00")


@pytest.mark.django_db
def test_scale_copy_leaves_the_original_alone(auth_client, recipe, iir):
    """The original keeps its servings and quantities."""
    _copy(auth_client, recipe, "6")
    recipe.refresh_from_db()
    iir.refresh_from_db()
    assert recipe.servings == 4
    assert iir.quantity == Decimal("2.00")


@pytest.mark.django_db
def test_scale_copy_keeps_servings_and_quantities_in_step(auth_client, user, group, make_iir):
    """3 servings scaled to 1 stores 1 serving with amounts for 1, not 2 with amounts for 1.5."""
    r = group.recipe
    r.servings = 3
    r.save()
    make_iir("rice-scale", Decimal("300"), unit="g")
    _copy(auth_client, r, "1")
    copy = Recipe.objects.exclude(pk=r.pk).get()
    assert copy.servings == 1
    assert IngredientInRecipe.objects.get(ingredient_group__recipe=copy).quantity == Decimal(
        "100.00"
    )


@pytest.mark.django_db
def test_scale_copy_skips_null_quantities(auth_client, recipe, make_iir):
    """Rows without a quantity stay without one."""
    make_iir("salt-copy", None)
    _copy(auth_client, recipe, "8")
    copy = Recipe.objects.exclude(pk=recipe.pk).get()
    assert IngredientInRecipe.objects.get(ingredient_group__recipe=copy).quantity is None


@pytest.mark.django_db
def test_scale_copy_quantity_exact_half_rounds_up(auth_client, recipe, make_iir):
    """0.05 for 4 is 0.025 for 2 → 0.03 with ROUND_HALF_UP, not 0.02."""
    make_iir("half-rounding", Decimal("0.05"), unit="g")
    _copy(auth_client, recipe, "2")
    copy = Recipe.objects.exclude(pk=recipe.pk).get()
    assert IngredientInRecipe.objects.get(ingredient_group__recipe=copy).quantity == Decimal("0.03")


@pytest.mark.django_db
def test_scale_copy_htmx_redirects_to_the_copy(auth_client, recipe, iir):
    """HTMX: HX-Redirect to the new recipe."""
    response = _copy(auth_client, recipe, "6", HTTP_HX_REQUEST="true")
    copy = Recipe.objects.exclude(pk=recipe.pk).get()
    assert response.status_code == 200
    assert response["HX-Redirect"] == copy.get_absolute_url()


@pytest.mark.django_db
def test_scale_copy_non_htmx_redirects_to_the_copy(auth_client, recipe, iir):
    """Plain POST: 302 to the new recipe."""
    response = _copy(auth_client, recipe, "6")
    copy = Recipe.objects.exclude(pk=recipe.pk).get()
    assert response.status_code == 302
    assert response["Location"] == copy.get_absolute_url()


@pytest.mark.parametrize("raw", ["abc", "0", "-1", "1.5", "99999", ""])
@pytest.mark.django_db
def test_scale_copy_invalid_servings_returns_422(auth_client, recipe, iir, raw):
    """A bad serving count re-renders the panel with an error and creates nothing."""
    response = _copy(auth_client, recipe, raw)
    assert response.status_code == 422
    assert "form-error" in response.content.decode()
    assert Recipe.objects.count() == 1


@pytest.mark.django_db
def test_scale_copy_quantity_overflow_returns_422(auth_client, recipe, make_iir):
    """A scaled quantity beyond DecimalField(max_digits=7, dp=2) rejects the copy."""
    make_iir("bulk-flour", Decimal("99999.00"), unit="g")
    response = _copy(auth_client, recipe, "6")
    assert response.status_code == 422
    assert "bulk-flour would be too large at 6 servings." in response.content.decode()
    assert Recipe.objects.count() == 1
    assert IngredientInRecipe.objects.count() == 1


@pytest.mark.django_db
def test_scale_copy_quantity_rounding_to_zero_returns_422(auth_client, recipe, make_iir):
    """0.01 for 4 is 0.0025 for 1, which two decimals would store as 0: refuse."""
    make_iir("saffron-copy", Decimal("0.01"), unit="g")
    response = _copy(auth_client, recipe, "1")
    assert response.status_code == 422
    assert "saffron-copy would round to 0 at 1 serving." in response.content.decode()
    assert Recipe.objects.count() == 1
