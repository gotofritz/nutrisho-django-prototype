"""Tests for migration 0033: recipes get UUID keys (#156, plan 012 M2).

Django's own `AlterField` copies each integer id as its decimal text, so recipe
10 would become the string `10` and no recipe would load. The migration rewrites
the ids, and the foreign keys to them, as 32-digit hex: recipe 10 becomes
`00000000-0000-0000-0000-00000000000a`.
"""

import uuid

import pytest

from recipes.models import Recipe
from recipes.services.recipe_export import export_recipes

BEFORE = [("recipes", "0032_private_units")]
AFTER = [("recipes", "0033_recipe_uuid_keys")]


def _without_timestamp(document: dict) -> dict:
    return {key: value for key, value in document.items() if key != "exported_at"}


def _numbered_recipe(apps, *, user, pk: int, name: str):
    """Recipe `pk`, the old kind, with a step, a group with a row, and a tag."""
    recipe = apps.get_model("recipes", "Recipe").objects.create(
        pk=pk, recipe_name=name, plain_name=name, owner_id=user.pk, servings=2
    )
    apps.get_model("recipes", "Step").objects.create(
        recipe=recipe, step_text=f"Cook {name}.", index_in_sequence=0
    )
    group = apps.get_model("recipes", "IngredientGroup").objects.create(
        recipe=recipe, group_name="Main", index_in_sequence=0
    )
    ingredient = apps.get_model("recipes", "Ingredient").objects.create(
        ingredient_name=f"{name}-salt"
    )
    apps.get_model("recipes", "IngredientInRecipe").objects.create(
        ingredient=ingredient, ingredient_group=group, index_in_sequence=0
    )
    apps.get_model("recipes", "Tag").objects.create(tag=f"{name}-tag").recipes.add(recipe)
    return recipe


@pytest.mark.django_db(transaction=True)
def test_numbered_recipes_keep_their_contents_under_the_uuid_of_their_number(user, migrate_to):
    """Recipe 10 becomes ...00a, and its steps, groups, rows and tags follow it."""
    old = migrate_to(BEFORE)
    _numbered_recipe(old, user=user, pk=10, name="soup")
    _numbered_recipe(old, user=user, pk=255, name="stew")

    migrate_to(AFTER)

    soup = Recipe.objects.get(pk=uuid.UUID("00000000-0000-0000-0000-00000000000a"))
    stew = Recipe.objects.get(pk=uuid.UUID(int=255))
    assert soup.recipe_name == "soup"
    assert [s.step_text for s in soup.steps.all()] == ["Cook soup."]
    assert [t.tag for t in soup.tags.all()] == ["soup-tag"]
    rows = soup.ingredient_groups.get().items.all()
    assert [r.ingredient.ingredient_name for r in rows] == ["soup-salt"]
    assert [t.tag for t in stew.tags.all()] == ["stew-tag"]
    assert list(Recipe.objects.order_by("id").values_list("recipe_name", flat=True)) == [
        "soup",
        "stew",
    ]


@pytest.mark.django_db(transaction=True)
def test_a_new_recipe_after_the_migration_sorts_after_the_numbered_ones(user, migrate_to):
    """New ids are version 7, so ordering by id is still ordering by age."""
    old = migrate_to(BEFORE)
    _numbered_recipe(old, user=user, pk=7, name="old")

    migrate_to(AFTER)
    new = Recipe.objects.create(recipe_name="new", owner=user)

    assert new.pk.version == 7
    assert list(Recipe.objects.order_by("id").values_list("recipe_name", flat=True)) == [
        "old",
        "new",
    ]


@pytest.mark.django_db(transaction=True)
def test_an_export_is_the_same_after_a_trip_back_and_forth(rich_recipe, user, migrate_to):
    """Steps, groups, tags and a trashed recipe export the same before and after."""
    before = export_recipes(owner=user)
    assert len(before["recipes"]) == 2  # one live, one in the trash

    migrate_to(BEFORE)
    migrate_to(AFTER)

    assert _without_timestamp(export_recipes(owner=user)) == _without_timestamp(before)


@pytest.mark.django_db(transaction=True)
def test_going_back_numbers_the_recipes_in_age_order(user, migrate_to):
    """A numbered recipe keeps its number; newer ones get the next numbers, oldest first."""
    old = migrate_to(BEFORE)
    _numbered_recipe(old, user=user, pk=10, name="kept")
    migrate_to(AFTER)
    first = Recipe.objects.create(recipe_name="first", owner=user)
    second = Recipe.objects.create(recipe_name="second", owner=user)
    first.tags.create(tag="first-tag")
    first.steps.create(step_text="Go.", index_in_sequence=0)
    assert first.pk < second.pk

    old = migrate_to(BEFORE)

    recipes = old.get_model("recipes", "Recipe").objects
    assert list(recipes.order_by("id").values_list("id", "recipe_name")) == [
        (10, "kept"),
        (11, "first"),
        (12, "second"),
    ]
    renumbered = recipes.get(pk=11)
    assert [s.step_text for s in renumbered.steps.all()] == ["Go."]
    assert [t.tag for t in renumbered.tags.all()] == ["first-tag"]
    assert [s.step_text for s in recipes.get(pk=10).steps.all()] == ["Cook kept."]
