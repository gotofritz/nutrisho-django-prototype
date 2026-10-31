"""Tests for the recipe duplication service (#35)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.db.models import Model
from django.test.utils import CaptureQueriesContext

from recipes.models import (
    Cuisine,
    Ingredient,
    IngredientGroup,
    IngredientInRecipe,
    Recipe,
    Source,
    Step,
    Tag,
)
from recipes.services.recipe_duplication import duplicate_recipe

# Fields a duplicate is expected to change rather than copy.
_NOT_COPIED: dict[type[Model], set[str]] = {
    Recipe: {"id", "recipe_name", "created_date"},
    Step: {"id", "recipe"},
    IngredientGroup: {"id", "recipe"},
    IngredientInRecipe: {"id", "ingredient_group"},
}


def _copied_fields(model: type[Model]) -> list:
    fields = model._meta.concrete_fields  # ty: ignore[unresolved-attribute]  # no Django stubs
    return [f for f in fields if f.name not in _NOT_COPIED[model]]


def _assert_every_field_copied(original: Model, copy: Model) -> None:
    for field in _copied_fields(type(original)):
        value = getattr(original, field.attname)
        # Guards the fixture: a new column left at its default would compare
        # equal whether or not it was copied, so it must be filled in below.
        assert value != field.get_default(), (
            f"populated_recipe leaves {type(original).__name__}.{field.name} at its "
            "default — give it a non-default value so the copy is tested"
        )
        assert getattr(copy, field.attname) == value, (
            f"{type(original).__name__}.{field.name} was not copied"
        )


@pytest.fixture
def populated_recipe(user):
    """A recipe with a non-default value in every copied column."""
    recipe = Recipe.objects.create(
        recipe_name="Original",
        owner=user,
        short_description="A blurb",
        source=Source.objects.create(short_name="Big Book", source="isbn:123"),
        source_instance="p. 42",
        cuisine=Cuisine.objects.create(cuisine="Thai"),
        servings=6,
    )
    Step.objects.create(
        recipe=recipe,
        step_title="Prep",
        step_text="Chop everything",
        index_in_sequence=1,
        duration=timedelta(minutes=10),
        extra_info="Use a sharp knife",
    )
    group = IngredientGroup.objects.create(recipe=recipe, group_name="Paste", index_in_sequence=1)
    IngredientInRecipe.objects.create(
        ingredient=Ingredient.objects.create(ingredient_name="chilli"),
        substitute=Ingredient.objects.create(ingredient_name="paprika"),
        unit="g",
        preparation="chopped",
        quantity=Decimal("12.50"),
        ingredient_group=group,
        index_in_sequence=1,
        note="fresh if possible",
    )
    Tag.objects.create(tag="spicy").recipe.add(recipe)
    return recipe


def _add_content(recipe: Recipe, *, groups: int, ingredients: int, steps: int) -> None:
    for s in range(steps):
        Step.objects.create(recipe=recipe, step_text=f"step {s}", index_in_sequence=s)
    for g in range(groups):
        group = IngredientGroup.objects.create(recipe=recipe, index_in_sequence=g)
        for i in range(ingredients):
            IngredientInRecipe.objects.create(
                ingredient=Ingredient.objects.get_or_create(ingredient_name=f"ing {i}")[0],
                substitute=Ingredient.objects.get_or_create(ingredient_name=f"sub {i}")[0],
                ingredient_group=group,
                index_in_sequence=i,
            )
    for t in range(3):
        Tag.objects.get_or_create(tag=f"tag {t}")[0].recipe.add(recipe)


@pytest.mark.django_db
def test_duplicate_copies_every_recipe_field(populated_recipe):
    """Every Recipe column except pk, name and creation date survives."""
    copy = duplicate_recipe(populated_recipe)
    assert copy.pk != populated_recipe.pk
    _assert_every_field_copied(populated_recipe, Recipe.objects.get(pk=copy.pk))


@pytest.mark.django_db
def test_duplicate_copies_every_step_field(populated_recipe):
    """Every Step column, step_title included, survives a duplicate."""
    copy = duplicate_recipe(populated_recipe)
    _assert_every_field_copied(
        Step.objects.get(recipe=populated_recipe), Step.objects.get(recipe=copy)
    )


@pytest.mark.django_db
def test_duplicate_copies_every_ingredient_group_field(populated_recipe):
    """Every IngredientGroup column survives a duplicate."""
    copy = duplicate_recipe(populated_recipe)
    _assert_every_field_copied(
        IngredientGroup.objects.get(recipe=populated_recipe),
        IngredientGroup.objects.get(recipe=copy),
    )


@pytest.mark.django_db
def test_duplicate_copies_every_ingredient_in_recipe_field(populated_recipe):
    """Every IngredientInRecipe column survives a duplicate."""
    copy = duplicate_recipe(populated_recipe)
    _assert_every_field_copied(
        IngredientInRecipe.objects.get(ingredient_group__recipe=populated_recipe),
        IngredientInRecipe.objects.get(ingredient_group__recipe=copy),
    )


@pytest.mark.django_db
def test_duplicate_leaves_original_children_in_place(populated_recipe):
    """Copied children belong to the copy; the original keeps its own."""
    copy = duplicate_recipe(populated_recipe)
    for recipe in (populated_recipe, copy):
        assert Step.objects.filter(recipe=recipe).count() == 1
        assert IngredientGroup.objects.filter(recipe=recipe).count() == 1
        assert IngredientInRecipe.objects.filter(ingredient_group__recipe=recipe).count() == 1
        assert list(Tag.objects.filter(recipe=recipe).values_list("tag", flat=True)) == ["spicy"]


@pytest.mark.django_db
def test_duplicate_keeps_ingredients_in_their_groups(user):
    """Each copied ingredient lands in the copy of its own group."""
    recipe = Recipe.objects.create(recipe_name="Two groups", owner=user)
    _add_content(recipe, groups=2, ingredients=2, steps=0)
    first = IngredientGroup.objects.get(recipe=recipe, index_in_sequence=0)
    IngredientInRecipe.objects.filter(ingredient_group=first).update(note="first")
    copy = duplicate_recipe(recipe)
    copied_first = IngredientGroup.objects.get(recipe=copy, index_in_sequence=0)
    assert set(
        IngredientInRecipe.objects.filter(ingredient_group=copied_first).values_list(
            "note", flat=True
        )
    ) == {"first"}


@pytest.mark.django_db
def test_duplicate_query_count_does_not_grow_with_recipe_size(user):
    """A six-group, 120-ingredient, 30-step recipe costs as many queries as a tiny one."""
    small = Recipe.objects.create(recipe_name="Small", owner=user)
    _add_content(small, groups=1, ingredients=1, steps=1)
    large = Recipe.objects.create(recipe_name="Large", owner=user)
    _add_content(large, groups=6, ingredients=20, steps=30)

    with CaptureQueriesContext(connection) as small_queries:
        duplicate_recipe(Recipe.objects.get(pk=small.pk))
    with CaptureQueriesContext(connection) as large_queries:
        duplicate_recipe(Recipe.objects.get(pk=large.pk))

    assert len(large_queries) == len(small_queries)
