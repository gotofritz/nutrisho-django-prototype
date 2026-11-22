"""Tests for reading and writing imported recipes (#78)."""

import json
from decimal import Decimal

import pytest

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step, Tag
from recipes.models.recipe import PROSE_MAX_LENGTH
from recipes.services import recipe_document
from recipes.services.recipe_document import (
    ImportBatch,
    ImportFormatError,
    RecipeDraft,
    parse_document,
)
from recipes.services.recipe_export import export_recipes
from recipes.services.recipe_import import import_recipes
from recipes.services.recipe_trash import purge_recipe


def _without_timestamp(document: dict) -> dict:
    return {key: value for key, value in document.items() if key != "exported_at"}


def _import(owner, document: object):
    return import_recipes(owner=owner, batch=parse_document(json.loads(json.dumps(document))))


def _minimal(**recipe: object) -> dict:
    return {"format": "nutrisho", "version": 1, "recipes": [{"recipe_name": "Soup", **recipe}]}


# --- the round trip ------------------------------------------------------


@pytest.mark.django_db
def test_round_trip_to_another_user_loses_nothing(user, other_user, rich_recipe):
    """Another user's import exports exactly the document it came from.

    Their account cannot see `user`'s private ingredient or tag, so the import
    makes its own, with the same display data.
    """
    document = export_recipes(owner=user)
    result = _import(other_user, document)
    assert result.warnings == []
    assert not any(imported.renamed for imported in result.recipes)
    assert _without_timestamp(export_recipes(owner=other_user)) == _without_timestamp(document)
    aubergine = Ingredient.objects.get(ingredient_name="aubergine-x", owner=other_user)
    assert aubergine.plural_name == "aubergines-x"
    assert Tag.objects.filter(tag="favourite", owner=other_user).exists()


@pytest.mark.django_db
def test_round_trip_after_deleting_everything(user, rich_recipe):
    """A user who exports, deletes every recipe and imports gets them all back."""
    document = export_recipes(owner=user)
    for recipe in Recipe.objects.filter(owner=user):
        purge_recipe(recipe)
    _import(user, document)
    assert _without_timestamp(export_recipes(owner=user)) == _without_timestamp(document)


@pytest.mark.django_db
def test_import_keeps_existing_recipes_and_renames_the_newcomer(user, rich_recipe):
    """Importing a name the user already has adds " Imported"; a trashed recipe keeps its name."""
    document = export_recipes(owner=user)
    first = _import(user, document)
    second = _import(user, document)
    names = [r.recipe.recipe_name for r in [*first.recipes, *second.recipes]]
    assert names == [
        "<u>Pasta</u> alla Norma Imported",
        "Old soup",
        "<u>Pasta</u> alla Norma Imported 2",
        "Old soup",
    ]
    assert first.recipes[0].renamed
    assert first.recipes[0].requested_name == "<u>Pasta</u> alla Norma"
    assert not first.recipes[1].renamed
    assert Recipe.objects.live().filter(owner=user).count() == 3


@pytest.mark.django_db
def test_import_finds_existing_ingredients_and_leaves_them_alone(user, other_user):
    """An ingredient the user can see is used as it is; the document's display data is not applied."""
    onion = Ingredient.objects.create(ingredient_name="onion", plural_name="")
    document = _minimal(ingredient_groups=[{"items": [{"ingredient": "Onions"}]}])
    document["ingredients"] = [{"ingredient_name": "Onions", "plural_name": "oniony"}]
    _import(user, document)
    row = IngredientInRecipe.objects.get(ingredient_group__recipe__owner=user)
    assert row.ingredient == onion
    onion.refresh_from_db()
    assert onion.plural_name == ""


@pytest.mark.django_db
def test_import_leaves_out_a_cuisine_it_cannot_place(user):
    """A cuisine too deep to place is left out, and the import says so; one it lacks is made (#171)."""
    result = _import(user, _minimal(cuisine="med.italy.sicily.palermo"))
    assert Recipe.objects.get(owner=user).cuisine is None
    assert result.warnings == [
        (
            "“Soup”: the cuisine “med.italy.sicily.palermo” was left out: "
            "Cuisines go at most 3 levels deep (area.region.subregion)."
        )
    ]


@pytest.mark.django_db
def test_import_warns_of_a_bad_cuisine_on_each_recipe(user):
    """Two recipes with the same unplaceable cuisine are each reported."""
    document = _minimal(cuisine="north")
    document["recipes"].append({"recipe_name": "Stew", "cuisine": "North"})
    result = _import(user, document)
    assert [w.split(":")[0] for w in result.warnings] == ["“Soup”", "“Stew”"]


@pytest.mark.django_db
def test_import_with_defaults(user):
    """A recipe needs only a name; the rest takes the column defaults."""
    result = _import(user, _minimal())
    recipe = result.recipes[0].recipe
    assert recipe.servings == 1
    assert recipe.short_description == ""
    assert recipe.deleted_at is None
    assert recipe.created_date is not None


@pytest.mark.django_db
def test_import_numbers_rows_in_order(user):
    """Steps, groups and rows take the positions of their list order."""
    document = _minimal(
        steps=[{"step_text": "One"}, {"step_text": "Two"}],
        ingredient_groups=[
            {"group_name": "A", "items": [{"ingredient": "a1"}, {"ingredient": "a2"}]},
            {"group_name": "B", "items": [{"ingredient": "b1"}]},
        ],
    )
    recipe = _import(user, document).recipes[0].recipe
    assert [(s.step_text, s.index_in_sequence) for s in recipe.steps.all()] == [
        ("One", 0),
        ("Two", 1),
    ]
    assert [
        (g.group_name, [(i.ingredient.ingredient_name, i.index_in_sequence) for i in g.items.all()])
        for g in recipe.ingredient_groups.all()
    ] == [("A", [("a1", 0), ("a2", 1)]), ("B", [("b1", 0)])]


@pytest.mark.django_db
def test_import_of_nothing(user):
    """An empty batch writes nothing."""
    assert import_recipes(owner=user, batch=ImportBatch(recipes=())).recipes == []
    assert not Recipe.objects.exists()


@pytest.mark.django_db
def test_import_draft_directly(user):
    """The writer takes drafts from any reader."""
    result = import_recipes(owner=user, batch=ImportBatch(recipes=(RecipeDraft(recipe_name="X"),)))
    assert result.recipes[0].recipe.recipe_name == "X"


# --- reading a Nutrisho document ------------------------------------------


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"format": "other"}, "Unknown format 'other': expected 'nutrisho'."),
        (
            {"format": "nutrisho", "version": 2},
            "Unsupported version 2: this server reads version 1.",
        ),
        ({"format": "nutrisho", "version": 1, "recipes": {}}, "document.recipes must be a list."),
        (
            {"format": "nutrisho", "version": 1, "recipes": [3]},
            "document.recipes[0] must be an object.",
        ),
        (_minimal(recipe_name=" "), "document.recipes[0].recipe_name is required."),
        (_minimal(recipe_name=3), "document.recipes[0].recipe_name must be text."),
        (_minimal(servings=0), "document.recipes[0].servings must be from 1 to 32767."),
        (_minimal(servings="4"), "document.recipes[0].servings must be a whole number."),
        (_minimal(servings=True), "document.recipes[0].servings must be a whole number."),
        (_minimal(tags="a, b"), "document.recipes[0].tags must be a list of text."),
        (
            _minimal(created_date="yesterday"),
            "document.recipes[0].created_date must be an ISO 8601 date and time.",
        ),
        (
            _minimal(created_date=5),
            "document.recipes[0].created_date must be an ISO 8601 date and time.",
        ),
        (
            _minimal(steps=[{"step_title": "x"}]),
            "document.recipes[0].steps[0].step_text is required.",
        ),
        (
            _minimal(ingredient_groups=[{"items": [{"quantity": "1"}]}]),
            "document.recipes[0].ingredient_groups[0].items[0].ingredient is required.",
        ),
        (
            _minimal(ingredient_groups=[{"items": [{"ingredient": "a", "quantity": "lots"}]}]),
            "document.recipes[0].ingredient_groups[0].items[0].quantity must be a number.",
        ),
        (
            _minimal(ingredient_groups=[{"items": [{"ingredient": "a", "quantity": [1]}]}]),
            "document.recipes[0].ingredient_groups[0].items[0].quantity must be a number.",
        ),
        (
            _minimal(ingredient_groups=[{"items": [{"ingredient": "a", "quantity": "-1"}]}]),
            "document.recipes[0].ingredient_groups[0].items[0].quantity must be from 0 to below 100000.",
        ),
        (
            _minimal(ingredient_groups=[{"items": [{"ingredient": "a", "quantity": "NaN"}]}]),
            "document.recipes[0].ingredient_groups[0].items[0].quantity must be from 0 to below 100000.",
        ),
        (
            _minimal(ingredient_groups=[{"items": [{"ingredient": "a", "quantity": "1.005"}]}]),
            "document.recipes[0].ingredient_groups[0].items[0].quantity has more than two decimals.",
        ),
        (
            {
                "format": "nutrisho",
                "version": 1,
                "ingredients": [{"ingredient_name": "a", "family": "XXX"}],
            },
            "document.ingredients[0].family must be one of",
        ),
    ],
)
def test_parse_document_refuses_a_bad_document(document: dict, message: str):
    """Each problem is named by where it is, before anything is written."""
    with pytest.raises(ImportFormatError) as raised:
        parse_document(document)
    assert str(raised.value).startswith(message)


def test_parse_document_reads_quantities_and_times():
    """A number or a decimal string is a quantity; a time without a zone is UTC."""
    document = _minimal(
        created_date="2024-01-02T03:04:05",
        ingredient_groups=[
            {"items": [{"ingredient": "a", "quantity": 2}, {"ingredient": "b", "quantity": "0.5"}]}
        ],
    )
    draft = parse_document(document).recipes[0]
    assert [row.quantity for row in draft.ingredient_groups[0].items] == [
        Decimal(2),
        Decimal("0.5"),
    ]
    assert draft.created_date is not None
    assert draft.created_date.isoformat() == "2024-01-02T03:04:05+00:00"


# --- reading schema.org JSON-LD ------------------------------------------


@pytest.mark.django_db
def test_parse_document_reads_json_ld():
    """A scraped Recipe becomes one recipe with one unnamed group, units resolved."""
    node = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": "Pancakes &amp; syrup",
        "description": "<p>Fluffy.</p>",
        "recipeYield": ["4", "4 pancakes"],
        "recipeCuisine": "American",
        "keywords": "easy, best pancakes",
        "url": "https://example.com/pancakes",
        "recipeIngredient": ["200 g flour", "2 large eggs", "Salt, to taste"],
        "recipeInstructions": [
            {"@type": "HowToStep", "text": "Mix."},
            {"@type": "HowToStep", "name": "Cook", "text": "Fry in a pan."},
        ],
    }
    (draft,) = parse_document({"@graph": [{"@type": "WebSite"}, node]}).recipes
    assert draft.recipe_name == "Pancakes & syrup"
    assert draft.short_description == "Fluffy."
    assert draft.servings == 4
    assert draft.source_instance == "https://example.com/pancakes"
    assert draft.cuisine == "American"
    assert draft.tags == ()
    assert [(s.step_title, s.step_text) for s in draft.steps] == [
        ("", "Mix."),
        ("Cook", "Fry in a pan."),
    ]
    (group,) = draft.ingredient_groups
    assert group.group_name == ""
    assert [(r.quantity, r.unit, r.ingredient, r.preparation, r.note) for r in group.items] == [
        (Decimal(200), "g", "flour", "", ""),
        (Decimal(2), "", "eggs", "large", ""),
        (None, "", "Salt", "", "to taste"),
    ]


@pytest.mark.django_db
def test_parse_document_json_ld_fallbacks():
    """No name, yield or ingredients: an untitled recipe for one, with no groups."""
    (draft,) = parse_document(
        {"@type": "Recipe", "url": "https://example.com/" + "x" * 300}
    ).recipes
    assert draft.recipe_name == "Untitled recipe"
    assert draft.servings == 1
    assert draft.source_instance == ""
    assert draft.ingredient_groups == ()


def test_parse_document_with_no_recipe():
    """Neither format: say what was expected."""
    with pytest.raises(ImportFormatError, match="No recipe found"):
        parse_document({"@type": "WebPage"})


@pytest.mark.django_db
def test_json_ld_import_writes_a_recipe(user):
    """End to end: a scraped recipe is written for the user, ingredients private to them."""
    batch = parse_document(
        {"@type": "Recipe", "name": "Toast", "recipeIngredient": ["2 slices bread"]}
    )
    (imported,) = import_recipes(owner=user, batch=batch).recipes
    row = IngredientInRecipe.objects.get(ingredient_group__recipe=imported.recipe)
    assert row.quantity == 2
    assert row.ingredient.owner == user


def test_parse_json_refuses_what_the_decoder_cannot_nest(monkeypatch):
    """A RecursionError from the decoder is a refusal, not a crash."""

    def _too_deep(_text: str) -> object:
        raise RecursionError

    monkeypatch.setattr(recipe_document.json, "loads", _too_deep)
    with pytest.raises(ImportFormatError, match="nested too deeply"):
        recipe_document.parse_json(b"[]")


# --- column lengths -------------------------------------------------------

_ROW = {"ingredient": "a"}


def _sized(where: str, key: str, value: str) -> dict:
    """A minimal document with `value` under `key` at `where`."""
    if where == "recipe":
        return _minimal(**{key: value})
    if where == "tag":
        return _minimal(tags=[value])
    if where == "step":
        return _minimal(steps=[{"step_text": "x", key: value}])
    if where == "group":
        return _minimal(ingredient_groups=[{key: value, "items": [_ROW]}])
    if where == "row":
        return _minimal(ingredient_groups=[{"items": [_ROW | {key: value}]}])
    document = _minimal()
    document["ingredients"] = [{"ingredient_name": "a", key: value}]
    return document


_PATHS = {
    "recipe": "document.recipes[0].{key}",
    "tag": "document.recipes[0].tags[0]",
    "step": "document.recipes[0].steps[0].{key}",
    "group": "document.recipes[0].ingredient_groups[0].{key}",
    "row": "document.recipes[0].ingredient_groups[0].items[0].{key}",
    "ingredient": "document.ingredients[0].{key}",
}
_LIMITS = [
    ("recipe", "recipe_name", Recipe, "recipe_name"),
    ("recipe", "source_instance", Recipe, "source_instance"),
    ("recipe", "short_description", None, None),
    ("tag", "tags", Tag, "tag"),
    ("step", "step_title", Step, "step_title"),
    ("step", "step_text", None, None),
    ("group", "group_name", IngredientGroup, "group_name"),
    ("row", "ingredient", Ingredient, "ingredient_name"),
    ("row", "substitute", Ingredient, "ingredient_name"),
    ("row", "unit", IngredientInRecipe, "legacy_unit"),
    ("row", "legacy_unit", IngredientInRecipe, "legacy_unit"),
    ("row", "preparation", IngredientInRecipe, "preparation"),
    ("row", "note", IngredientInRecipe, "note"),
    ("ingredient", "ingredient_name", Ingredient, "ingredient_name"),
    ("ingredient", "plural_name", Ingredient, "plural_name"),
]


@pytest.mark.parametrize(
    ("where", "key", "model", "column"), _LIMITS, ids=[f"{w}-{k}" for w, k, _, _ in _LIMITS]
)
def test_parse_document_refuses_text_longer_than_its_column(where, key, model, column):
    """SQLite does not enforce `max_length`, so the reader does; long prose has the form's cap."""
    limit = model._meta.get_field(column).max_length if model else PROSE_MAX_LENGTH
    parse_document(_sized(where, key, "x" * limit))
    with pytest.raises(ImportFormatError) as raised:
        parse_document(_sized(where, key, "x" * (limit + 1)))
    path = _PATHS[where].format(key=key)
    assert str(raised.value) == f"{path} must be at most {limit} characters."


@pytest.mark.django_db
def test_parse_document_cuts_json_ld_to_its_columns():
    """A scraped recipe is never refused for length: its text is cut to fit."""
    node = {
        "@type": "Recipe",
        "name": "Soup",
        "description": "d" * 5000,
        "recipeIngredient": ["2 onions, " + "p" * 300 + " (" + "n" * 300 + ")"],
        "recipeInstructions": "s" * 5000,
    }
    (draft,) = parse_document(node).recipes
    assert draft.short_description == "d" * PROSE_MAX_LENGTH
    assert draft.steps[0].step_text == "s" * PROSE_MAX_LENGTH
    (row,) = draft.ingredient_groups[0].items
    assert row.preparation == "p" * 128
    assert row.note == "n" * 128
