"""Read an import into drafts: a Nutrisho document, or schema.org Recipe JSON-LD (#78).

A Nutrisho document is what `recipe_export.export_recipes` writes:

    {
      "format": "nutrisho", "version": 1, "exported_at": "<ISO 8601>",
      "ingredients": [
        {"ingredient_name", "plural_name", "family", "dietary_constraint"}, ...
      ],
      "recipes": [
        {
          "recipe_name", "short_description", "servings", "source_instance",
          "cuisine": "<dotted path>", "tags": ["<name>", ...],
          "created_date": "<ISO 8601>", "deleted_at": "<ISO 8601>" | null,
          "steps": [{"step_title", "step_text"}, ...],
          "ingredient_groups": [
            {"group_name", "items": [
              {"ingredient", "substitute", "quantity": "<decimal>" | null,
               "unit", "legacy_unit", "preparation", "note"}, ...
            ]}, ...
          ]
        }, ...
      ]
    }

Keys are the model's column names. Text is as typed, inline markup included;
lists are in display order; a missing key takes the column's default. Text
longer than its column (long prose: than the editor's `PROSE_MAX_LENGTH`) is
refused, since SQLite would store it whole. The `ingredients` list carries the
display data of the ingredients the recipes use, which an import gives a new
private ingredient; one it already finds keeps its own.

Anything else is searched for schema.org `Recipe` nodes (`utils/json_ld.py`),
which hold far less and are cut to fit the columns rather than refused: their
ingredient lines are read by `utils/ingredient_line.py` into one unnamed group,
and tags are not taken from `keywords`, which sites fill for search engines.

Nothing here writes; `recipe_import.import_recipes` writes the drafts.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Model

from recipes.models import (
    Cuisine,
    Ingredient,
    IngredientGroup,
    IngredientInRecipe,
    Recipe,
    Step,
    Tag,
)
from recipes.models.recipe import PROSE_MAX_LENGTH
from recipes.services.name_resolution import find_unit
from recipes.utils.ingredient_line import parse_ingredient_line
from recipes.utils.json_ld import (
    find_recipes,
    ingredient_lines,
    instruction_steps,
    servings_from_yield,
    text_of,
)
from recipes.utils.scaling import MAX_SERVINGS

FORMAT = "nutrisho"
VERSION = 1


def _max_length(model: type[Model], column: str) -> int:
    return model._meta.get_field(column).max_length  # ty: ignore[unresolved-attribute]  # no Django stubs


# SQLite does not enforce a column's `max_length`, so the reader does (#78). Long
# prose is a TextField with no limit of its own; the editor's forms cap it.
_NAME_MAX_LENGTH = _max_length(Recipe, "recipe_name")
_SOURCE_MAX_LENGTH = _max_length(Recipe, "source_instance")
_TAG_MAX_LENGTH = _max_length(Tag, "tag")
_STEP_TITLE_MAX_LENGTH = _max_length(Step, "step_title")
_GROUP_NAME_MAX_LENGTH = _max_length(IngredientGroup, "group_name")
_INGREDIENT_MAX_LENGTH = _max_length(Ingredient, "ingredient_name")
_PLURAL_MAX_LENGTH = _max_length(Ingredient, "plural_name")
_UNIT_MAX_LENGTH = _max_length(IngredientInRecipe, "legacy_unit")
_PREPARATION_MAX_LENGTH = _max_length(IngredientInRecipe, "preparation")
_NOTE_MAX_LENGTH = _max_length(IngredientInRecipe, "note")
# Not a column: a dotted path of up to three cuisine names, looked up, never stored.
_CUISINE_PATH_MAX_LENGTH = 3 * _max_length(Cuisine, "cuisine") + 2
# The length each text field of a recipe in a document may have, by its key: what
# the reader below refuses past, and what the clipper loads to flag a field
# before it saves (#160). `tags` is the length of each tag.
FIELD_LENGTHS: dict[str, int] = {
    "recipe_name": _NAME_MAX_LENGTH,
    "short_description": PROSE_MAX_LENGTH,
    "source_instance": _SOURCE_MAX_LENGTH,
    "cuisine": _CUISINE_PATH_MAX_LENGTH,
    "tags": _TAG_MAX_LENGTH,
    "step_title": _STEP_TITLE_MAX_LENGTH,
    "step_text": PROSE_MAX_LENGTH,
    "group_name": _GROUP_NAME_MAX_LENGTH,
    "ingredient": _INGREDIENT_MAX_LENGTH,
    "substitute": _INGREDIENT_MAX_LENGTH,
    "unit": _UNIT_MAX_LENGTH,
    "legacy_unit": _UNIT_MAX_LENGTH,
    "preparation": _PREPARATION_MAX_LENGTH,
    "note": _NOTE_MAX_LENGTH,
}
_QUANTITY_LIMIT = Decimal(100000)  # IngredientInRecipe.quantity: 7 digits, 2 decimals
_CENT = Decimal("0.01")
_FAMILIES = {code for code, _ in Ingredient.GROUP_CHOICES}
_DIETS = {code for code, _ in Ingredient.CONSTRAINT_CHOICES}
UNTITLED = "Untitled recipe"


class ImportFormatError(ValueError):
    """The data is not something an import can read; the message says where and why."""


@dataclass(frozen=True)
class RowDraft:
    """One ingredient row, by names; the unit is resolved when it is written."""

    ingredient: str
    substitute: str = ""
    quantity: Decimal | None = None
    unit: str = ""
    legacy_unit: str = ""
    preparation: str = ""
    note: str = ""


@dataclass(frozen=True)
class GroupDraft:
    """One ingredient group and its rows, in order."""

    group_name: str = ""
    items: tuple[RowDraft, ...] = ()


@dataclass(frozen=True)
class StepDraft:
    """One step."""

    step_text: str
    step_title: str = ""


@dataclass(frozen=True)
class RecipeDraft:
    """One recipe to write, with its cuisine and tags by name."""

    recipe_name: str
    short_description: str = ""
    servings: int = 1
    source_instance: str = ""
    cuisine: str = ""
    tags: tuple[str, ...] = ()
    created_date: datetime | None = None
    deleted_at: datetime | None = None
    steps: tuple[StepDraft, ...] = ()
    ingredient_groups: tuple[GroupDraft, ...] = ()


@dataclass(frozen=True)
class IngredientDraft:
    """The display data a new ingredient of this name is given."""

    ingredient_name: str
    plural_name: str = ""
    family: str = ""
    dietary_constraint: str = ""


@dataclass(frozen=True)
class ImportBatch:
    """The recipes in an import, and display data for their ingredients by lower-case name."""

    recipes: tuple[RecipeDraft, ...]
    ingredients: dict[str, IngredientDraft] = field(default_factory=dict)


def parse_document(data: object) -> ImportBatch:
    """Read `data`, already decoded from JSON, or raise `ImportFormatError`."""
    if isinstance(data, dict) and "format" in data:
        return _read_nutrisho(data)
    nodes = find_recipes(data)
    if not nodes:
        msg = "No recipe found: expected a Nutrisho export or schema.org Recipe JSON-LD."
        raise ImportFormatError(msg)
    is_unit = _unit_checker()
    return ImportBatch(recipes=tuple(_from_json_ld(node, is_unit=is_unit) for node in nodes))


def parse_json(raw: bytes) -> ImportBatch:
    """Decode `raw` as UTF-8 JSON and read it, or raise `ImportFormatError`."""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except UnicodeDecodeError:
        msg = "This is not UTF-8 text."
        raise ImportFormatError(msg) from None
    except json.JSONDecodeError as exc:
        msg = f"This is not JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}."
        raise ImportFormatError(msg) from None
    except RecursionError:
        msg = "This JSON is nested too deeply."
        raise ImportFormatError(msg) from None
    return parse_document(data)


# --- Nutrisho documents ---------------------------------------------------


class _Reader:
    """Typed access to one JSON object, naming `path` in every error."""

    def __init__(self, data: object, *, path: str) -> None:
        if not isinstance(data, dict):
            msg = f"{path} must be an object."
            raise ImportFormatError(msg)
        self._data: dict[str, object] = data
        self._path = path

    def _fail(self, key: str, problem: str) -> ImportFormatError:
        return ImportFormatError(f"{self._path}.{key} {problem}.")

    def text(self, key: str, *, max_length: int, required: bool = False) -> str:
        value = self._data.get(key)
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise self._fail(key, "must be text")
        if required and not value.strip():
            raise self._fail(key, "is required")
        if len(value) > max_length:
            raise self._fail(key, f"must be at most {max_length} characters")
        return value

    def choice(self, key: str, *, allowed: set[str]) -> str:
        value = self.text(key, max_length=max(len(code) for code in allowed))
        if value and value not in allowed:
            raise self._fail(key, f"must be one of {', '.join(sorted(allowed))}")
        return value

    def servings(self, key: str) -> int:
        value = self._data.get(key, 1)
        if isinstance(value, bool) or not isinstance(value, int):
            raise self._fail(key, "must be a whole number")
        if not 1 <= value <= MAX_SERVINGS:
            raise self._fail(key, f"must be from 1 to {MAX_SERVINGS}")
        return value

    def quantity(self, key: str) -> Decimal | None:
        value = self._data.get(key)
        if value is None or value == "":
            return None
        if isinstance(value, bool) or not isinstance(value, str | int | float):
            raise self._fail(key, "must be a number")
        try:
            quantity = Decimal(str(value))
        except InvalidOperation:
            raise self._fail(key, "must be a number") from None
        if not quantity.is_finite() or not 0 <= quantity < _QUANTITY_LIMIT:
            raise self._fail(key, f"must be from 0 to below {_QUANTITY_LIMIT}")
        if quantity != quantity.quantize(_CENT):
            raise self._fail(key, "has more than two decimals")
        return quantity

    def when(self, key: str) -> datetime | None:
        value = self._data.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise self._fail(key, "must be an ISO 8601 date and time")
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            raise self._fail(key, "must be an ISO 8601 date and time") from None
        return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)

    def texts(self, key: str, *, max_length: int) -> tuple[str, ...]:
        value = self._data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise self._fail(key, "must be a list of text")
        for index, item in enumerate(value):
            if len(item) > max_length:
                raise self._fail(f"{key}[{index}]", f"must be at most {max_length} characters")
        return tuple(v for v in value if v.strip())

    def objects(self, key: str) -> list[_Reader]:
        value = self._data.get(key, [])
        if not isinstance(value, list):
            raise self._fail(key, "must be a list")
        return [_Reader(item, path=f"{self._path}.{key}[{i}]") for i, item in enumerate(value)]


def _read_nutrisho(data: dict) -> ImportBatch:
    if data.get("format") != FORMAT:
        msg = f"Unknown format {data.get('format')!r}: expected {FORMAT!r}."
        raise ImportFormatError(msg)
    if data.get("version") != VERSION:
        msg = f"Unsupported version {data.get('version')!r}: this server reads version {VERSION}."
        raise ImportFormatError(msg)
    document = _Reader(data, path="document")
    ingredients = {}
    for item in document.objects("ingredients"):
        draft = IngredientDraft(
            ingredient_name=item.text(
                "ingredient_name", max_length=_INGREDIENT_MAX_LENGTH, required=True
            ),
            plural_name=item.text("plural_name", max_length=_PLURAL_MAX_LENGTH),
            family=item.choice("family", allowed=_FAMILIES),
            dietary_constraint=item.choice("dietary_constraint", allowed=_DIETS),
        )
        ingredients.setdefault(draft.ingredient_name.strip().lower(), draft)
    recipes = tuple(_read_recipe(recipe) for recipe in document.objects("recipes"))
    return ImportBatch(recipes=recipes, ingredients=ingredients)


def _read_recipe(recipe: _Reader) -> RecipeDraft:
    return RecipeDraft(
        recipe_name=recipe.text(
            "recipe_name", max_length=FIELD_LENGTHS["recipe_name"], required=True
        ),
        short_description=recipe.text(
            "short_description", max_length=FIELD_LENGTHS["short_description"]
        ),
        servings=recipe.servings("servings"),
        source_instance=recipe.text("source_instance", max_length=FIELD_LENGTHS["source_instance"]),
        cuisine=recipe.text("cuisine", max_length=FIELD_LENGTHS["cuisine"]),
        tags=recipe.texts("tags", max_length=FIELD_LENGTHS["tags"]),
        created_date=recipe.when("created_date"),
        deleted_at=recipe.when("deleted_at"),
        steps=tuple(
            StepDraft(
                step_title=step.text("step_title", max_length=FIELD_LENGTHS["step_title"]),
                step_text=step.text(
                    "step_text", max_length=FIELD_LENGTHS["step_text"], required=True
                ),
            )
            for step in recipe.objects("steps")
        ),
        ingredient_groups=tuple(
            GroupDraft(
                group_name=group.text("group_name", max_length=FIELD_LENGTHS["group_name"]),
                items=tuple(_read_row(row) for row in group.objects("items")),
            )
            for group in recipe.objects("ingredient_groups")
        ),
    )


def _read_row(row: _Reader) -> RowDraft:
    return RowDraft(
        ingredient=row.text("ingredient", max_length=FIELD_LENGTHS["ingredient"], required=True),
        substitute=row.text("substitute", max_length=FIELD_LENGTHS["substitute"]),
        quantity=row.quantity("quantity"),
        unit=row.text("unit", max_length=FIELD_LENGTHS["unit"]),
        legacy_unit=row.text("legacy_unit", max_length=FIELD_LENGTHS["legacy_unit"]),
        preparation=row.text("preparation", max_length=FIELD_LENGTHS["preparation"]),
        note=row.text("note", max_length=FIELD_LENGTHS["note"]),
    )


# --- schema.org JSON-LD ---------------------------------------------------


def _unit_checker():
    """`find_unit` as a yes or no, remembering each answer for this import.

    Parsing knows no owner, so a line's unit is recognised from the global
    units only; a user's own unit stays part of the ingredient's name.
    """
    answers: dict[str, bool] = {}

    def is_unit(text: str) -> bool:
        key = text.lower()
        if key not in answers:
            answers[key] = find_unit(text, owner=None) is not None
        return answers[key]

    return is_unit


def _from_json_ld(node: dict[str, object], *, is_unit) -> RecipeDraft:
    source = text_of(node.get("url") or node.get("mainEntityOfPage"))
    rows = []
    for line in ingredient_lines(node.get("recipeIngredient") or node.get("ingredients")):
        parsed = parse_ingredient_line(line, is_unit=is_unit)
        rows.append(
            RowDraft(
                ingredient=parsed.name,
                quantity=parsed.quantity,
                unit=parsed.unit,
                preparation=parsed.preparation[:_PREPARATION_MAX_LENGTH],
                note=parsed.note[:_NOTE_MAX_LENGTH],
            )
        )
    return RecipeDraft(
        recipe_name=text_of(node.get("name"))[:_NAME_MAX_LENGTH] or UNTITLED,
        short_description=text_of(node.get("description"))[:PROSE_MAX_LENGTH],
        servings=servings_from_yield(node.get("recipeYield")) or 1,
        # A web address cut short is a broken link: leave it out instead.
        source_instance=source if len(source) <= _SOURCE_MAX_LENGTH else "",
        cuisine=text_of(node.get("recipeCuisine")),
        steps=tuple(
            StepDraft(step_title=title, step_text=text[:PROSE_MAX_LENGTH])
            for title, text in instruction_steps(node.get("recipeInstructions"))
        ),
        ingredient_groups=(GroupDraft(items=tuple(rows)),) if rows else (),
    )
