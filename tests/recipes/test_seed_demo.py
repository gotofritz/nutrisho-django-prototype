"""Tests for the seed_demo management command (#71)."""

import re
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step, Tag
from recipes.services.ingredient_admin import (
    find_ingredient_duplicates,
    find_plural_duplicates,
    search_ingredients,
)


def seed(**options) -> str:
    """Run seed_demo and return what it printed."""
    out = StringIO()
    call_command("seed_demo", stdout=out, **options)
    return out.getvalue()


def demo_recipes(username: str = "demo"):
    """The recipes the seed gave `username`."""
    return Recipe.objects.filter(owner__username=username)


def row_counts() -> dict[str, int]:
    """How many rows each seeded model holds."""
    models = (User, Recipe, Ingredient, IngredientGroup, IngredientInRecipe, Step, Tag)
    return {model.__name__: model.objects.count() for model in models}


@pytest.mark.django_db
def test_refuses_to_run_under_production_settings(settings):
    """Demo data never lands in the real database."""
    settings.SETTINGS_MODULE = "nutrisho.settings.prod"

    with pytest.raises(CommandError, match="production"):
        seed()

    assert not User.objects.exists()
    assert not Recipe.objects.exists()


@pytest.mark.django_db
def test_creates_a_staff_demo_user_with_a_printed_password():
    """The demo user can log in, with a random password shown once, and use the staff tools."""
    output = seed()

    demo = User.objects.get(username="demo")
    assert demo.is_staff
    assert not demo.is_superuser
    password = re.search(r"password (\S+)", output)
    assert password is not None
    assert demo.check_password(password.group(1))


@pytest.mark.django_db
def test_seeds_several_recipes_for_the_demo_user():
    """Every seeded recipe belongs to the demo user, and nobody else gets any."""
    seed()

    assert demo_recipes().count() >= 4
    assert Recipe.objects.count() == demo_recipes().count()


@pytest.mark.django_db
def test_leaves_singular_plural_pairs_for_the_clean_up_tool():
    """A rule plural (onions) and an override plural (chillies) sit next to their singulars."""
    seed()

    pairs = {tuple(i.ingredient_name for i in pair) for pair in find_plural_duplicates()}
    assert ("onion", "onions") in pairs
    assert ("chilli", "chillies") in pairs


@pytest.mark.django_db
def test_leaves_a_case_duplicate_and_a_spelling_variant():
    """A private `Onion` clashes with the global `onion`; eggplant is aubergine by another name."""
    seed()

    groups = [{i.ingredient_name for i in group} for group in find_ingredient_duplicates()]
    assert {"onion", "Onion"} in groups
    used = set(IngredientInRecipe.objects.values_list("ingredient__ingredient_name", flat=True))
    assert {"aubergine", "eggplant"} <= used


@pytest.mark.django_db
def test_leaves_private_and_unused_ingredients():
    """The demo user owns private rows to promote, and one global row is an orphan."""
    seed()
    demo = User.objects.get(username="demo")

    assert Ingredient.objects.filter(owner=demo).count() >= 2
    assert search_ingredients("", unused_only=True).filter(owner__isnull=True).exists()


@pytest.mark.django_db
def test_covers_plural_overrides():
    """One ingredient carries a plural override, another is invariant."""
    seed()

    assert Ingredient.objects.get(ingredient_name="chilli", owner=None).plural == "chillies"
    assert Ingredient.objects.get(ingredient_name="broccoli", owner=None).plural == "broccoli"


@pytest.mark.django_db
def test_covers_groups_substitutes_and_step_titles():
    """Some recipes have named groups, a substitute and titled steps; some have none."""
    seed()
    group_counts = [r.ingredients_group.count() for r in demo_recipes()]

    assert max(group_counts) >= 2
    assert min(group_counts) == 1
    assert IngredientGroup.objects.exclude(group_name="").exists()
    assert IngredientInRecipe.objects.filter(substitute__isnull=False).exists()
    assert Step.objects.exclude(step_title="").exists()
    assert Step.objects.filter(step_title="").exists()


@pytest.mark.django_db
def test_covers_markup_tags_and_cuisines():
    """Titles and blurbs carry inline tags; recipes have global and private tags and cuisines."""
    seed()
    demo = User.objects.get(username="demo")

    assert demo_recipes().filter(recipe_name__contains="<").exists()
    assert demo_recipes().filter(short_description__contains="<").exists()
    assert demo_recipes().filter(cuisine__isnull=False).exists()
    assert Tag.objects.filter(owner__isnull=True, recipe__owner=demo).exists()
    assert Tag.objects.filter(owner=demo, recipe__owner=demo).exists()


@pytest.mark.django_db
def test_every_seeded_recipe_page_renders(client):
    """The seeded data is valid for the app: each recipe page loads for its owner."""
    seed()
    client.force_login(User.objects.get(username="demo"))

    for recipe in demo_recipes():
        response = client.get(reverse("recipes:recipe", kwargs={"recipe_id": recipe.pk}))
        assert response.status_code == 200


@pytest.mark.django_db
def test_running_twice_adds_nothing():
    """A second run finds every recipe in place and writes nothing."""
    seed()
    before = row_counts()

    output = seed()

    assert row_counts() == before
    assert "already" in output


@pytest.mark.django_db
def test_reset_rebuilds_the_demo_recipes_and_their_duplicates():
    """After the clean-up tool merged a pair, --reset brings the demo data back."""
    seed()
    Recipe.objects.filter(owner__username="demo").delete()
    Ingredient.objects.filter(ingredient_name="onions").delete()
    demo = User.objects.get(username="demo")
    Recipe.objects.create(owner=demo, recipe_name="My own recipe")

    seed(reset=True)

    assert demo_recipes().filter(recipe_name="My own recipe").exists()
    assert Ingredient.objects.filter(ingredient_name="onions").exists()
    assert demo_recipes().count() >= 5


@pytest.mark.django_db
def test_reset_replaces_existing_demo_recipes():
    """--reset deletes the demo recipes it finds before creating them again."""
    seed()
    first_ids = set(demo_recipes().values_list("pk", flat=True))

    seed(reset=True)

    assert demo_recipes().count() == len(first_ids)
    assert not demo_recipes().filter(pk__in=first_ids).exists()


@pytest.mark.django_db
def test_seeds_an_existing_user_without_touching_the_account(user):
    """--username puts the recipes in an existing account; its password and flags stay."""
    output = seed(username=user.username)

    user.refresh_from_db()
    assert user.check_password("x")
    assert not user.is_staff
    assert demo_recipes(user.username).count() >= 4
    assert not User.objects.filter(username="demo").exists()
    assert "password" not in output
    assert "staff" in output
