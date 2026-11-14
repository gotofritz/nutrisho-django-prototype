"""Tests for exporting a user's recipes as a Nutrisho document (#78)."""

import json

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step
from recipes.services.recipe_export import export_recipes

# Columns an export leaves out, each for a reason: ids and owners belong to
# this database, `plain_*` are derived on save, and a position is list order.
NOT_EXPORTED = {
    Recipe: {"id", "owner", "plain_name", "plain_description"},
    Step: {"id", "recipe", "index_in_sequence"},
    IngredientGroup: {"id", "recipe", "index_in_sequence"},
    IngredientInRecipe: {"id", "ingredient_group", "index_in_sequence"},
    Ingredient: {"id", "owner"},
}


def _columns(model) -> set[str]:
    return {f.name for f in model._meta.concrete_fields} - NOT_EXPORTED[model]


@pytest.mark.django_db
def test_export_names_its_format(user):
    """The document says what it is, so an import can refuse anything else."""
    document = export_recipes(owner=user)
    assert document["format"] == "nutrisho"
    assert document["version"] == 1
    assert document["recipes"] == []
    assert document["ingredients"] == []


@pytest.mark.django_db
def test_export_is_json(user, rich_recipe):
    """The document survives `json.dumps` and back unchanged."""
    document = export_recipes(owner=user)
    assert json.loads(json.dumps(document)) == document


@pytest.mark.django_db
def test_export_carries_every_column(user, rich_recipe):
    """Every column a recipe holds is in the export, so a new one cannot be forgotten.

    A new column on any of these models fails here until the export writes it,
    or `NOT_EXPORTED` says why it need not.
    """
    document = export_recipes(owner=user)
    recipe = document["recipes"][0]
    assert _columns(Recipe) | {"tags", "steps", "ingredient_groups"} == set(recipe)
    assert _columns(Step) == set(recipe["steps"][0])
    assert _columns(IngredientGroup) | {"items"} == set(recipe["ingredient_groups"][0])
    assert _columns(IngredientInRecipe) == set(recipe["ingredient_groups"][0]["items"][0])
    assert _columns(Ingredient) == set(document["ingredients"][0])


@pytest.mark.django_db
def test_export_values(user, rich_recipe):
    """Markup as typed, quantities exact, names rather than ids, children in order."""
    document = export_recipes(owner=user)
    live, trashed = document["recipes"]
    assert live == {
        "recipe_name": "<u>Pasta</u> alla Norma",
        "short_description": "Rich\nand <i>warm</i>",
        "servings": 4,
        "source_instance": "https://example.com/norma",
        "cuisine": "med.italy.sicily",
        "tags": ["dinner", "favourite"],
        "created_date": "2024-01-02T03:04:00+00:00",
        "deleted_at": None,
        "steps": [
            {"step_title": "Prep", "step_text": "Chop the <b>aubergine</b>."},
            {"step_title": "", "step_text": "Fry."},
        ],
        "ingredient_groups": [
            {
                "group_name": "Sauce",
                "items": [
                    {
                        "ingredient": "aubergine-x",
                        "substitute": "courgette-x",
                        "quantity": "1.50",
                        "unit": "kg",
                        "legacy_unit": "",
                        "preparation": "cubed",
                        "note": "firm ones",
                    },
                    {
                        "ingredient": "basil-x",
                        "substitute": "",
                        "quantity": None,
                        "unit": "",
                        "legacy_unit": "handful",
                        "preparation": "torn",
                        "note": "",
                    },
                ],
            },
            {
                "group_name": "Pasta",
                "items": [
                    {
                        "ingredient": "rigatoni-x",
                        "substitute": "",
                        "quantity": "400.00",
                        "unit": "g",
                        "legacy_unit": "",
                        "preparation": "",
                        "note": "",
                    }
                ],
            },
        ],
    }
    assert trashed["recipe_name"] == "Old soup"
    assert trashed["deleted_at"] == "2025-05-06T00:00:00+00:00"


@pytest.mark.django_db
def test_export_lists_the_ingredients_it_uses(user, rich_recipe):
    """Each ingredient and substitute once, sorted, with its display data."""
    document = export_recipes(owner=user)
    assert document["ingredients"] == [
        {
            "ingredient_name": "aubergine-x",
            "plural_name": "aubergines-x",
            "family": "VEG",
            "dietary_constraint": "VGN",
        },
        {"ingredient_name": "basil-x", "plural_name": "", "family": "", "dietary_constraint": ""},
        {
            "ingredient_name": "courgette-x",
            "plural_name": "",
            "family": "",
            "dietary_constraint": "",
        },
        {
            "ingredient_name": "rigatoni-x",
            "plural_name": "",
            "family": "",
            "dietary_constraint": "",
        },
    ]


@pytest.mark.django_db
def test_export_leaves_out_other_users_recipes(user, other_user, rich_recipe, make_recipe):
    """Only the owner's recipes, live and trashed."""
    make_recipe(owner=other_user, name="Not mine")
    names = [r["recipe_name"] for r in export_recipes(owner=user)["recipes"]]
    assert names == ["<u>Pasta</u> alla Norma", "Old soup"]
    assert [r["recipe_name"] for r in export_recipes(owner=other_user)["recipes"]] == ["Not mine"]


@pytest.mark.django_db
def test_export_queries_do_not_grow_with_recipe_count(user, rich_recipe):
    """Ten recipes cost the same queries as one: everything is prefetched."""
    with CaptureQueriesContext(connection) as one:
        export_recipes(owner=user)
    for n in range(10):
        recipe = Recipe.objects.create(recipe_name=f"More {n}", owner=user, servings=1)
        group = IngredientGroup.objects.create(recipe=recipe, index_in_sequence=0)
        IngredientInRecipe.objects.create(
            ingredient_group=group,
            index_in_sequence=0,
            ingredient=Ingredient.objects.create(ingredient_name=f"more {n}"),
        )
        Step.objects.create(recipe=recipe, step_text="Stir.", index_in_sequence=0)
    with CaptureQueriesContext(connection) as many:
        export_recipes(owner=user)
    assert len(many.captured_queries) == len(one.captured_queries)
