"""Tests for recipes views."""

import pytest
from django.test import Client

from recipes.models import Recipe


@pytest.fixture
def auth_client(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def recipe(user, db):
    return Recipe.objects.create(recipe_name="Test Recipe", owner=user)


@pytest.fixture
def two_recipes(user, db):
    r1 = Recipe.objects.create(recipe_name="First", owner=user)
    r2 = Recipe.objects.create(recipe_name="Second", owner=user)
    return r1, r2


@pytest.mark.django_db
def test_home_view_returns_200(auth_client):
    response = auth_client.get("/recipes/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_home_view_lists_recipes(auth_client, recipe):
    response = auth_client.get("/recipes/")
    assert response.status_code == 200
    assert recipe in response.context["latest_recipe_list"]


@pytest.mark.django_db
def test_recipe_view_returns_200(auth_client, recipe):
    response = auth_client.get(f"/recipes/{recipe.pk}/")
    assert response.status_code == 200
    assert response.context["recipe"] == recipe


@pytest.mark.django_db
def test_recipe_view_404_on_missing(auth_client, db):
    response = auth_client.get("/recipes/99999/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_recipe_nav_single_recipe_wraps_to_self(auth_client, recipe):
    response = auth_client.get(f"/recipes/{recipe.pk}/")
    nav = response.context["nav"]
    assert nav["prev_id"] == recipe.pk
    assert nav["next_id"] == recipe.pk


@pytest.mark.django_db
def test_recipe_nav_wraps_at_boundaries(auth_client, two_recipes):
    first, second = two_recipes
    # At last recipe, next wraps to first
    response = auth_client.get(f"/recipes/{second.pk}/")
    nav = response.context["nav"]
    assert nav["next_id"] == first.pk
    # At first recipe, prev wraps to last
    response = auth_client.get(f"/recipes/{first.pk}/")
    nav = response.context["nav"]
    assert nav["prev_id"] == second.pk


@pytest.mark.django_db
def test_serves_field_always_editable(auth_client, user):
    """Detail page always shows the Serves inline-edit widget."""
    r = Recipe.objects.create(recipe_name="Mystery Soup", owner=user)
    response = auth_client.get(f"/recipes/{r.pk}/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Serves" in content
    assert f"/recipes/{r.pk}/field/servings/edit/" in content


@pytest.mark.django_db
def test_serves_label_shown_when_servings_set(auth_client, user):
    """Detail page renders 'Serves' label and the servings value when set."""
    r = Recipe.objects.create(recipe_name="Known Soup", owner=user, servings=4)
    response = auth_client.get(f"/recipes/{r.pk}/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Serves" in content
    assert "4" in content


@pytest.mark.django_db
def test_field_display_has_data_empty_when_value_blank(auth_client, user):
    """Empty editable fields get data-empty attr so print CSS can hide them."""
    r = Recipe.objects.create(recipe_name="No Desc", owner=user, short_description="")
    response = auth_client.get(f"/recipes/{r.pk}/")
    content = response.content.decode()
    assert 'class="editable field-short_description" data-empty' in content


@pytest.mark.django_db
def test_field_display_no_data_empty_when_value_present(auth_client, user):
    r = Recipe.objects.create(recipe_name="Has Desc", owner=user, short_description="Tasty soup")
    response = auth_client.get(f"/recipes/{r.pk}/")
    content = response.content.decode()
    assert 'field-short_description" data-empty' not in content


@pytest.mark.django_db
def test_recipe_detail_has_inline_edit_triggers(auth_client, recipe):
    """Recipe detail page includes hx-get triggers for field inline editing."""
    response = auth_client.get(f"/recipes/{recipe.pk}/")
    content = response.content.decode()
    field_edit_url = f"/recipes/{recipe.pk}/field/recipe_name/edit/"
    assert field_edit_url in content


@pytest.mark.django_db
def test_list_delete_button_has_hx_confirm(auth_client, recipe):
    """Recipe list page includes delete button with hx-confirm."""
    response = auth_client.get("/recipes/")
    content = response.content.decode()
    assert "hx-confirm" in content
    assert f"/recipes/{recipe.pk}/delete/" in content


@pytest.mark.django_db
def test_list_has_new_recipe_link(auth_client):
    """Recipe list page includes 'New Recipe' link."""
    response = auth_client.get("/recipes/")
    assert b"/recipes/new/" in response.content


@pytest.mark.django_db
def test_field_edit_short_description_is_textarea(auth_client, recipe):
    response = auth_client.get(f"/recipes/{recipe.pk}/field/short_description/edit/")
    content = response.content.decode()
    assert "<textarea" in content
    assert 'name="short_description"' in content


@pytest.mark.django_db
def test_recipe_detail_query_count_constant(auth_client, user, django_assert_max_num_queries):
    """Detail page prefetches steps/groups/ingredients — no N+1 per row."""
    from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Step

    r = Recipe.objects.create(recipe_name="Prefetch Soup", owner=user)
    for i in range(4):
        Step.objects.create(recipe=r, step_text=f"Step {i}", index_in_sequence=i)
    for g in range(3):
        grp = IngredientGroup.objects.create(recipe=r, group_name=f"G{g}", index_in_sequence=g)
        for j in range(3):
            ing = Ingredient.objects.create(ingredient_name=f"ing-{g}-{j}")
            IngredientInRecipe.objects.create(
                ingredient=ing, ingredient_group=grp, index_in_sequence=j
            )
    with django_assert_max_num_queries(10):
        response = auth_client.get(f"/recipes/{r.pk}/")
    assert response.status_code == 200
