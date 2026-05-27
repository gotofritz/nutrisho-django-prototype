"""Tests for recipe duplication view."""

import pytest
from django.test import Client

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step, Tag


@pytest.fixture
def auth_client(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def recipe(user, db):
    return Recipe.objects.create(
        recipe_name="Original Recipe",
        owner=user,
        short_description="desc",
        servings=4,
    )


@pytest.fixture
def recipe_with_content(recipe):
    Step.objects.create(recipe=recipe, step_text="Step one", index_in_sequence=0)
    Step.objects.create(recipe=recipe, step_text="Step two", index_in_sequence=1)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="Main", index_in_sequence=0)
    ing = Ingredient.objects.create(ingredient_name="flour")
    IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=0, quantity=2, unit="cups"
    )
    return recipe


@pytest.mark.django_db
def test_duplicate_requires_post(auth_client, recipe):
    response = auth_client.get(f"/recipes/{recipe.pk}/duplicate/")
    assert response.status_code == 405


@pytest.mark.django_db
def test_duplicate_creates_new_recipe(auth_client, recipe):
    auth_client.post(f"/recipes/{recipe.pk}/duplicate/")
    assert Recipe.objects.count() == 2


@pytest.mark.django_db
def test_duplicate_name_has_copy_suffix(auth_client, recipe):
    auth_client.post(f"/recipes/{recipe.pk}/duplicate/")
    copy = Recipe.objects.exclude(pk=recipe.pk).get()
    assert copy.recipe_name == "Original Recipe Copy"


@pytest.mark.django_db
def test_duplicate_name_avoids_collision(auth_client, recipe, user):
    Recipe.objects.create(recipe_name="Original Recipe Copy", owner=user)
    auth_client.post(f"/recipes/{recipe.pk}/duplicate/")
    names = list(Recipe.objects.values_list("recipe_name", flat=True))
    assert "Original Recipe Copy 2" in names


@pytest.mark.django_db
def test_duplicate_copies_metadata(auth_client, recipe):
    auth_client.post(f"/recipes/{recipe.pk}/duplicate/")
    copy = Recipe.objects.exclude(pk=recipe.pk).get()
    assert copy.short_description == recipe.short_description
    assert copy.servings == recipe.servings


@pytest.mark.django_db
def test_duplicate_copies_steps(auth_client, recipe_with_content):
    auth_client.post(f"/recipes/{recipe_with_content.pk}/duplicate/")
    copy = Recipe.objects.exclude(pk=recipe_with_content.pk).get()
    assert Step.objects.filter(recipe=copy).count() == 2
    assert Step.objects.filter(recipe=copy, step_text="Step one").exists()


@pytest.mark.django_db
def test_duplicate_copies_ingredient_groups(auth_client, recipe_with_content):
    auth_client.post(f"/recipes/{recipe_with_content.pk}/duplicate/")
    copy = Recipe.objects.exclude(pk=recipe_with_content.pk).get()
    assert IngredientGroup.objects.filter(recipe=copy).count() == 1


@pytest.mark.django_db
def test_duplicate_copies_ingredients_in_groups(auth_client, recipe_with_content):
    auth_client.post(f"/recipes/{recipe_with_content.pk}/duplicate/")
    copy = Recipe.objects.exclude(pk=recipe_with_content.pk).get()
    group = IngredientGroup.objects.get(recipe=copy)
    assert IngredientInRecipe.objects.filter(ingredient_group=group).count() == 1


@pytest.mark.django_db
def test_duplicate_copies_tags(auth_client, recipe):
    vegan = Tag.objects.create(tag="vegan")
    quick = Tag.objects.create(tag="quick")
    vegan.recipe.add(recipe)
    quick.recipe.add(recipe)
    auth_client.post(f"/recipes/{recipe.pk}/duplicate/")
    copy = Recipe.objects.exclude(pk=recipe.pk).get()
    assert set(copy.tag.values_list("tag", flat=True)) == {"vegan", "quick"}
    # Original keeps its tags
    assert set(recipe.tag.values_list("tag", flat=True)) == {"vegan", "quick"}


@pytest.mark.django_db
def test_duplicate_redirects_to_copy(auth_client, recipe):
    response = auth_client.post(f"/recipes/{recipe.pk}/duplicate/")
    copy = Recipe.objects.exclude(pk=recipe.pk).get()
    assert response.status_code == 302
    assert response["Location"] == copy.get_absolute_url()


@pytest.mark.django_db
def test_duplicate_htmx_returns_hx_redirect(auth_client, recipe):
    """Boosted duplicate button must get HX-Redirect so URL/history update."""
    response = auth_client.post(f"/recipes/{recipe.pk}/duplicate/", HTTP_HX_REQUEST="true")
    copy = Recipe.objects.exclude(pk=recipe.pk).get()
    assert response.status_code == 200
    assert "HX-Redirect" in response
    assert response["HX-Redirect"] == copy.get_absolute_url()


@pytest.mark.django_db
def test_duplicate_200_char_name_does_not_exceed_max_length(auth_client, user):
    """Duplicating a 200-character name must produce a name ≤200 chars."""
    long_name = "X" * 200
    recipe = Recipe.objects.create(recipe_name=long_name, owner=user)
    auth_client.post(f"/recipes/{recipe.pk}/duplicate/")
    copy = Recipe.objects.exclude(pk=recipe.pk).get()
    assert len(copy.recipe_name) <= 200
    assert copy.recipe_name != long_name


@pytest.mark.django_db
def test_duplicate_near_max_length_collision_still_within_max(auth_client, user):
    """When Copy already exists, Copy 2 suffix must also respect max_length."""
    long_name = "X" * 200
    suffix = " Copy"
    trimmed = long_name[: 200 - len(suffix)]
    Recipe.objects.create(recipe_name=f"{trimmed}{suffix}", owner=user)
    recipe = Recipe.objects.create(recipe_name=long_name, owner=user)
    auth_client.post(f"/recipes/{recipe.pk}/duplicate/")
    copy = Recipe.objects.exclude(
        pk__in=[recipe.pk, Recipe.objects.filter(recipe_name=f"{trimmed}{suffix}").first().pk]
    ).get()
    assert len(copy.recipe_name) <= 200


@pytest.mark.django_db
def test_duplicate_child_integrity_error_propagates_not_loops(auth_client, recipe):
    """IntegrityError from child row copy must propagate, not trigger infinite name-retry loop."""
    from unittest.mock import patch

    from django.db import IntegrityError

    Step.objects.create(recipe=recipe, step_text="Step 1", index_in_sequence=0)
    count_before = Recipe.objects.filter(owner=recipe.owner).count()

    with patch("recipes.models.Step.save", side_effect=IntegrityError("dup seq")):
        with pytest.raises(IntegrityError):
            auth_client.post(f"/recipes/{recipe.pk}/duplicate/")

    # Transaction rolled back — no extra Recipe created
    assert Recipe.objects.filter(owner=recipe.owner).count() == count_before
