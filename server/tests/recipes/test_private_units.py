"""Private units: units become a shared vocabulary like ingredients (#154, plan 012 M1).

`Unit.owner` is NULL for the global, staff-curated list and a user for a unit
private to that user. Typing or importing an unknown unit makes a private one;
staff make it global by clearing its owner in admin.
"""

import json
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from recipes.models import Ingredient, IngredientInRecipe, Unit, UnitAlias
from recipes.services.name_resolution import find_unit, resolve_unit, unit_names
from recipes.services.recipe_document import parse_document
from recipes.services.recipe_export import export_recipes
from recipes.services.recipe_import import import_recipes


@pytest.fixture
def private_unit(db):
    """Make a unit private to `owner`, with no dimension."""

    def _make(name: str, *, owner) -> Unit:
        return Unit.objects.create(name=name, owner=owner)

    return _make


# --- Model -------------------------------------------------------------------


@pytest.mark.django_db
def test_seeded_units_are_global():
    """Every unit the vocabulary shipped with stays global."""
    assert not Unit.objects.filter(owner__isnull=False).exists()
    assert Unit.objects.get(name="tbsp").owner is None


@pytest.mark.django_db
def test_two_users_may_each_have_a_private_unit_with_the_same_name(private_unit, user, other_user):
    """Private names only clash within one owner."""
    private_unit("punnet", owner=user)
    private_unit("Punnet", owner=other_user)
    assert Unit.objects.filter(name__iexact="punnet").count() == 2


@pytest.mark.django_db
def test_one_user_cannot_have_two_private_units_differing_by_case(private_unit, user):
    """Within one owner, names are unique ignoring case."""
    private_unit("punnet", owner=user)
    with pytest.raises(IntegrityError), transaction.atomic():
        private_unit("PUNNET", owner=user)


@pytest.mark.django_db
def test_a_private_unit_has_no_dimension(private_unit, user):
    """Only staff know whether a user's word is a mass, a volume or a count."""
    unit = private_unit("punnet", owner=user)
    unit.full_clean()
    assert unit.dimension == ""


@pytest.mark.django_db
def test_a_global_unit_needs_a_dimension():
    """Making a unit global is when staff say what it measures."""
    with pytest.raises(ValidationError, match="dimension"):
        Unit(name="punnet").full_clean()


@pytest.mark.django_db
def test_clearing_the_owner_makes_a_private_unit_global(private_unit, user, other_user):
    """Staff promote a unit in admin by clearing its owner and giving it a dimension."""
    unit = private_unit("punnet", owner=user)
    unit.owner = None
    unit.dimension = Unit.COUNT
    unit.full_clean()
    unit.save()
    assert find_unit("punnet", owner=other_user) == unit


@pytest.mark.django_db
def test_a_private_unit_cannot_become_global_when_the_name_is_taken(private_unit, user):
    """The global list keeps its case-insensitive uniqueness."""
    unit = private_unit("Cup", owner=user)
    unit.owner = None
    unit.dimension = Unit.VOLUME
    with pytest.raises(ValidationError, match="already exists"):
        unit.full_clean()


@pytest.mark.django_db
def test_an_alias_may_only_name_a_global_unit(private_unit, user):
    """Aliases stay global: one user's unit is not everyone's spelling."""
    alias = UnitAlias(alias_name="pnt", unit=private_unit("punnet", owner=user))
    with pytest.raises(ValidationError, match="global unit"):
        alias.full_clean()


@pytest.mark.django_db
def test_an_alias_may_share_a_name_with_a_private_unit(private_unit, user):
    """Only a global unit's name is closed to aliases."""
    private_unit("tbso", owner=user)
    UnitAlias(alias_name="tbso", unit=Unit.objects.get(name="tbsp")).full_clean()


@pytest.mark.django_db
def test_deleting_a_user_deletes_their_private_units(private_unit, other_user):
    """Private units go with their owner."""
    unit = private_unit("punnet", owner=other_user)
    other_user.delete()
    assert not Unit.objects.filter(pk=unit.pk).exists()


def _admin_form(unit: Unit, **changes: str) -> dict[str, str]:
    data = {
        "name": str(unit.name),
        "plural_name": str(unit.plural_name),
        "dimension": str(unit.dimension),
        "owner": str(unit.owner_id or ""),
        "aliases-TOTAL_FORMS": "0",
        "aliases-INITIAL_FORMS": "0",
    }
    data.update(changes)
    return data


@pytest.mark.django_db
def test_admin_lists_units_with_their_owner(admin_client, private_unit, user):
    """Staff see whose a unit is, and can filter to the global ones."""
    private_unit("punnet", owner=user)
    html = admin_client.get("/admin/recipes/unit/?owner__isempty=0").content.decode()
    assert "punnet" in html
    assert user.username in html


@pytest.mark.django_db
def test_staff_make_a_unit_global_in_admin(admin_client, private_unit, user):
    """Clearing the owner and giving a dimension makes it everyone's."""
    unit = private_unit("punnet", owner=user)
    response = admin_client.post(
        f"/admin/recipes/unit/{unit.pk}/change/", _admin_form(unit, owner="", dimension="count")
    )
    assert response.status_code == 302
    unit.refresh_from_db()
    assert (unit.owner, unit.dimension) == (None, Unit.COUNT)


@pytest.mark.django_db
def test_admin_refuses_a_global_unit_without_a_dimension(admin_client, private_unit, user):
    """The form says what is missing, and the unit stays private."""
    unit = private_unit("punnet", owner=user)
    response = admin_client.post(
        f"/admin/recipes/unit/{unit.pk}/change/", _admin_form(unit, owner="")
    )
    assert "A global unit needs a dimension." in response.content.decode()
    unit.refresh_from_db()
    assert unit.owner == user


# --- Resolution --------------------------------------------------------------


@pytest.mark.django_db
def test_find_unit_sees_the_users_own_units_and_never_anyone_elses(private_unit, user, other_user):
    """A private unit is one user's vocabulary."""
    mine = private_unit("punnet", owner=user)
    assert find_unit("Punnets", owner=user) == mine
    assert find_unit("punnet", owner=other_user) is None
    assert find_unit("punnet", owner=None) is None


@pytest.mark.django_db
def test_find_unit_prefers_the_global_unit(private_unit, user):
    """Once staff have a unit of that name, it is the one everyone means."""
    private_unit("bushel", owner=user)
    bushel = Unit.objects.create(name="bushel", dimension=Unit.VOLUME)
    assert find_unit("bushel", owner=user) == bushel


@pytest.mark.django_db
def test_find_unit_by_alias_still_works_for_a_user(user):
    """Aliases are global, so every user's spelling resolves."""
    assert find_unit("tablespoons", owner=user) == Unit.objects.get(name="tbsp")


@pytest.mark.django_db
def test_resolve_unit_makes_a_private_unit_on_a_miss(user):
    """An unknown unit becomes the user's own, tidied as `find_unit` reads it."""
    unit = resolve_unit(" punnet. ", owner=user)
    assert unit is not None
    assert (unit.name, unit.owner, unit.dimension) == ("punnet", user, "")
    assert resolve_unit("Punnets", owner=user) == unit


@pytest.mark.django_db
def test_resolve_unit_never_copies_a_global_unit(user):
    """A spelling of a global unit, alias or plural included, is that unit."""
    before = Unit.objects.count()
    assert resolve_unit("Tablespoons", owner=user) == Unit.objects.get(name="tbsp")
    assert Unit.objects.count() == before


@pytest.mark.django_db
@pytest.mark.parametrize("typed", ["", "  ", "small", "Large", "to taste", "as needed"])
def test_resolve_unit_never_makes_a_unit_of_a_size_word_or_an_amount(user, typed):
    """`small` belongs in the preparation and `to taste` in the note."""
    before = Unit.objects.count()
    assert resolve_unit(typed, owner=user) is None
    assert Unit.objects.count() == before


@pytest.mark.django_db
def test_unit_names_lists_the_global_units_and_the_users_own(private_unit, user, other_user):
    """The editor suggests the user's units beside the global ones, never another user's."""
    private_unit("punnet", owner=user)
    private_unit("bale", owner=other_user)
    private_unit("CUP", owner=user)
    names = unit_names(owner=user)
    assert "punnet" in names
    assert "tbsp" in names
    assert "bale" not in names
    assert [name for name in names if name.lower() == "cup"] == ["cup"]
    assert names == sorted(names, key=str.lower)


# --- The editor --------------------------------------------------------------


@pytest.fixture
def garlic_row(user, make_recipe, add_ingredient, make_ingredient):
    """A recipe with one `2 clove garlic` row."""
    recipe = make_recipe(owner=user, name="Aioli")
    row = add_ingredient(
        recipe=recipe, ingredient=make_ingredient("garlic"), quantity=Decimal(2), unit="clove"
    )
    return recipe, row


def _save(client, recipe, row, unit: str):
    return client.post(
        f"/recipes/{recipe.pk}/ingredients/{row.pk}/save/",
        {"ingredient_name": "garlic", "quantity": "2", "unit": unit, "preparation": "", "note": ""},
    )


@pytest.mark.django_db
def test_editor_makes_an_unknown_unit_the_owners_own(auth_client, user, garlic_row):
    """Saving `punnet` stores a new private unit on the row, with no error."""
    recipe, row = garlic_row
    response = _save(auth_client, recipe, row, "punnet")
    assert "<form" not in response.content.decode()
    row.refresh_from_db()
    assert row.unit == Unit.objects.get(name="punnet", owner=user)
    assert '<span class="ingredient-unit">punnets</span>' in response.content.decode()


@pytest.mark.django_db
def test_editor_create_makes_an_unknown_unit_the_owners_own(auth_client, user, garlic_row):
    """A new row resolves an unknown unit the same way."""
    recipe, row = garlic_row
    auth_client.post(
        f"/recipes/{recipe.pk}/groups/{row.ingredient_group_id}/ingredients/create/",
        {"ingredient_name": "kale", "quantity": "1", "unit": "bunchlet"},
    )
    created = IngredientInRecipe.objects.get(ingredient__ingredient_name="kale")
    assert created.unit == Unit.objects.get(name="bunchlet", owner=user)


@pytest.mark.django_db
def test_editor_refusal_of_a_size_word_writes_nothing(auth_client, garlic_row):
    """`small` is still an error naming its field, and no unit is made."""
    recipe, row = garlic_row
    before = Unit.objects.count()
    content = _save(auth_client, recipe, row, "small").content.decode()
    assert "put it under preparation" in content
    assert Unit.objects.count() == before


@pytest.mark.django_db
def test_editor_suggests_the_owners_units_only(
    auth_client, user, other_user, private_unit, garlic_row
):
    """The datalist offers the user's own units, never another user's."""
    recipe, row = garlic_row
    private_unit("punnet", owner=user)
    private_unit("bale", owner=other_user)
    content = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{row.pk}/edit/").content.decode()
    assert '<option value="punnet">' in content
    assert '<option value="bale">' not in content


@pytest.mark.django_db
def test_another_users_unit_is_not_used_by_the_editor(
    auth_client, user, other_user, private_unit, garlic_row
):
    """Typing another user's unit makes the owner a unit of their own."""
    recipe, row = garlic_row
    theirs = private_unit("punnet", owner=other_user)
    _save(auth_client, recipe, row, "punnet")
    row.refresh_from_db()
    assert row.unit != theirs
    assert row.unit.owner == user


# --- Import and export -------------------------------------------------------


def _import(owner, items: list[dict]):
    document = {
        "format": "nutrisho",
        "version": 1,
        "recipes": [{"recipe_name": "Soup", "ingredient_groups": [{"items": items}]}],
    }
    return import_recipes(owner=owner, batch=parse_document(json.loads(json.dumps(document))))


@pytest.mark.django_db
def test_import_makes_an_unknown_unit_the_importers_own(user):
    """A unit the server lacks becomes the importer's, not legacy text."""
    result = _import(user, [{"ingredient": "basil", "unit": "bunchlet"}])
    row = IngredientInRecipe.objects.get(ingredient_group__recipe__owner=user)
    assert row.unit == Unit.objects.get(name="bunchlet", owner=user)
    assert row.legacy_unit == ""
    assert result.warnings == []


@pytest.mark.django_db
def test_import_keeps_a_size_word_as_written(user):
    """A size word never becomes a unit: the row keeps it as legacy text, with a warning."""
    result = _import(user, [{"ingredient": "onion", "unit": "small"}])
    row = IngredientInRecipe.objects.get(ingredient_group__recipe__owner=user)
    assert row.unit is None
    assert row.legacy_unit == "small"
    assert result.warnings == ["“Soup”: “small” is not a unit here, so it is kept as written."]


@pytest.mark.django_db
def test_import_makes_one_unit_for_every_row_that_names_it(user):
    """Two rows with the same unknown unit share one new unit."""
    _import(
        user,
        [{"ingredient": "basil", "unit": "bunchlet"}, {"ingredient": "mint", "unit": "Bunchlets"}],
    )
    assert Unit.objects.filter(owner=user).count() == 1


@pytest.mark.django_db
def test_a_private_unit_round_trips_to_another_user(
    user, other_user, private_unit, make_recipe, add_ingredient
):
    """Exported and imported by someone else, the unit becomes their own."""
    private_unit("punnet", owner=user)
    add_ingredient(
        recipe=make_recipe(owner=user, name="Jam"),
        ingredient=Ingredient.objects.create(ingredient_name="strawberry"),
        quantity=Decimal(2),
        unit="punnet",
    )
    document = export_recipes(owner=user)
    import_recipes(owner=other_user, batch=parse_document(json.loads(json.dumps(document))))
    row = IngredientInRecipe.objects.get(ingredient_group__recipe__owner=other_user)
    assert row.unit == Unit.objects.get(name="punnet", owner=other_user)
    assert export_recipes(owner=other_user)["recipes"] == document["recipes"]
