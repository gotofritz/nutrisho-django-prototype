"""The staff-only unit tool (#154).

Modelled on the cuisine and ingredient tools: a searchable list of every unit,
global and private, the staff member's recipes using the selection, and Add,
Edit, Promote, Merge and Delete actions.
"""

import re
from decimal import Decimal

import pytest
from django.test import Client

from recipes.models import Ingredient, IngredientInRecipe, Unit, UnitAlias
from recipes.services.unit_admin import (
    UnitScopeError,
    delete_units,
    merge_units,
    promote_units,
    unit_rows,
)

MANAGE = "/recipes/units/manage/"


@pytest.fixture
def staff_client(user):
    """The default user, made staff, logged in."""
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def other_client(other_user):
    """A signed-in user who is not staff."""
    client = Client()
    client.force_login(other_user)
    return client


@pytest.fixture
def private_unit(db):
    """Make a unit private to `owner`."""

    def _make(name: str, *, owner) -> Unit:
        return Unit.objects.create(name=name, owner=owner)

    return _make


@pytest.fixture
def row_with(make_recipe, add_ingredient):
    """A row in a new recipe of `owner`'s that uses `unit`."""

    def _make(unit: Unit, *, owner, recipe_name: str = "Jam") -> IngredientInRecipe:
        recipe = make_recipe(owner=owner, name=recipe_name)
        row = add_ingredient(
            recipe=recipe,
            ingredient=Ingredient.objects.get_or_create(ingredient_name="strawberry")[0],
            quantity=Decimal(2),
        )
        row.unit = unit
        row.save(update_fields=["unit"])
        return row

    return _make


def _unit(name: str) -> Unit:
    return Unit.objects.get(name=name, owner__isnull=True)


def _checked(html: str, unit: Unit) -> bool:
    """Whether the list ticks `unit`."""
    return re.search(rf'id="unit-pick-{unit.pk}"[^>]*\bchecked\b', html) is not None


# --- Access ----------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    ["", "columns/", "add/", "edit/", "promote/", "merge/", "delete/"],
    ids=lambda u: u or "page",
)
def test_every_read_route_is_staff_only(other_client, url):
    """Non-staff get 403 on every GET route."""
    assert other_client.get(MANAGE + url).status_code == 403


@pytest.mark.django_db
def test_mutations_are_staff_only_and_write_nothing(other_client, other_user, private_unit):
    """Non-staff POSTs are refused before anything is written."""
    punnet = private_unit("punnet", owner=other_user)
    cup = _unit("cup")
    before = Unit.objects.count()
    posts = [
        (MANAGE + "add/", {"name": "bale", "dimension": "count"}),
        (f"{MANAGE}{cup.pk}/save/", {"name": "mug", "dimension": "volume"}),
        (MANAGE + "promote/", {"unit_ids": [punnet.pk], "dimension": "count"}),
        (MANAGE + "merge/", {"unit_ids": [cup.pk, punnet.pk], "survivor_id": cup.pk}),
        (MANAGE + "delete/", {"unit_ids": [punnet.pk]}),
    ]
    for url, data in posts:
        assert other_client.post(url, data).status_code == 403
    assert Unit.objects.count() == before
    assert _unit("cup").name == "cup"
    punnet.refresh_from_db()
    assert punnet.owner == other_user


@pytest.mark.django_db
def test_config_links_the_tool_for_staff_only(staff_client, other_client):
    """The Config page lists Units beside Ingredients and Cuisines, for staff."""
    assert f'href="{MANAGE}"' in staff_client.get("/recipes/config/").content.decode()
    assert f'href="{MANAGE}"' not in other_client.get("/recipes/config/").content.decode()


# --- The list ----------------------------------------------------------------------


@pytest.mark.django_db
def test_rows_show_every_unit_with_owner_aliases_and_use(user, other_user, private_unit, row_with):
    """One row per unit, global and private, with what staff need to curate it."""
    punnet = private_unit("punnet", owner=other_user)
    row_with(punnet, owner=other_user)
    row_with(_unit("tbsp"), owner=user)
    rows = {row.unit.pk: row for row in unit_rows()}
    assert rows[punnet.pk].owner_name == other_user.username
    assert rows[punnet.pk].row_count == 1
    assert rows[_unit("tbsp").pk].owner_name == ""
    assert "tablespoon" in rows[_unit("tbsp").pk].aliases
    assert rows[_unit("tsp").pk].row_count == 0


@pytest.mark.django_db
def test_rows_search_names_and_aliases(private_unit, user):
    """`table` finds `tbsp` by its alias; a private unit by its name."""
    private_unit("tablet", owner=user)
    names = [row.unit.name for row in unit_rows("table")]
    assert "tbsp" in names
    assert "tablet" in names
    assert "cup" not in names


@pytest.mark.django_db
def test_rows_filter_private_and_unused(user, private_unit, row_with):
    """Private only lists what awaits curation; unused only what can go freely."""
    punnet = private_unit("punnet", owner=user)
    bale = private_unit("bale", owner=user)
    row_with(punnet, owner=user)
    assert {row.unit.name for row in unit_rows(private_only=True)} == {"punnet", "bale"}
    unused = {row.unit.pk for row in unit_rows(unused_only=True)}
    assert bale.pk in unused
    assert punnet.pk not in unused


@pytest.mark.django_db
def test_rows_sort_alphabetically_or_by_age(private_unit, user):
    """A to Z ignoring case by default; oldest first on request."""
    newest = private_unit("Aardvark", owner=user)
    names = [str(row.unit.name) for row in unit_rows()]
    assert names == sorted(names, key=str.lower)
    assert unit_rows(by_added=True)[-1].unit == newest


@pytest.mark.django_db
def test_page_lists_units_and_the_selection_lists_the_staff_members_recipes(
    staff_client, user, other_user, private_unit, row_with
):
    """Column 3 holds the staff member's own recipes using the selected units."""
    private_unit("punnet", owner=other_user)
    row_with(_unit("cup"), owner=user, recipe_name="Mine")
    row_with(_unit("cup"), owner=other_user, recipe_name="Theirs")
    html = staff_client.get(MANAGE, {"unit_ids": [_unit("cup").pk]}).content.decode()
    assert "punnet" in html
    assert other_user.username in html
    assert "Mine" in html
    assert "Theirs" not in html


@pytest.mark.django_db
def test_columns_keep_the_filters(staff_client, user, private_unit):
    """The columns endpoint applies search and the private filter."""
    private_unit("punnet", owner=user)
    html = staff_client.get(MANAGE + "columns/", {"q": "pun", "private": "1"}).content.decode()
    assert "punnet" in html
    assert 'id="unit-pick-' + str(_unit("cup").pk) + '"' not in html


# --- Add and edit ----------------------------------------------------------------


@pytest.mark.django_db
def test_add_creates_a_global_unit(staff_client):
    """A new unit is global, with its dimension and plural."""
    response = staff_client.post(
        MANAGE + "add/", {"name": " bale ", "plural_name": "", "dimension": "count"}
    )
    assert response.status_code == 200
    bale = _unit("bale")
    assert bale.dimension == Unit.COUNT
    assert _checked(response.content.decode(), bale)


@pytest.mark.django_db
def test_add_needs_a_dimension_and_a_free_name(staff_client):
    """Both come back as form errors, and nothing is written."""
    before = Unit.objects.count()
    missing = staff_client.post(MANAGE + "add/", {"name": "bale", "dimension": ""})
    assert missing.status_code == 422
    assert "A global unit needs a dimension." in missing.content.decode()
    taken = staff_client.post(MANAGE + "add/", {"name": "CUP", "dimension": "volume"})
    assert taken.status_code == 422
    assert "That unit already exists." in taken.content.decode()
    assert Unit.objects.count() == before


@pytest.mark.django_db
def test_edit_needs_exactly_one_selected(staff_client):
    """The guard says what to select."""
    response = staff_client.get(MANAGE + "edit/")
    assert response.status_code == 422
    assert "Select exactly 1 unit first." in response.content.decode()


@pytest.mark.django_db
def test_edit_form_shows_the_unit_and_its_aliases(staff_client):
    """Prefilled with the name, dimension and other spellings."""
    html = staff_client.get(MANAGE + "edit/", {"unit_ids": [_unit("tbsp").pk]}).content.decode()
    assert 'value="tbsp"' in html
    assert "tablespoon" in html


@pytest.mark.django_db
def test_edit_renames_and_sets_aliases(staff_client):
    """Aliases are typed comma-separated: new ones are added, missing ones removed."""
    cup = _unit("cup")
    response = staff_client.post(
        f"{MANAGE}{cup.pk}/save/",
        {"name": "cup", "plural_name": "", "dimension": "volume", "aliases": "mug, Beaker"},
    )
    assert response.status_code == 200
    assert sorted(UnitAlias.objects.filter(unit=cup).values_list("alias_name", flat=True)) == [
        "Beaker",
        "mug",
    ]


@pytest.mark.django_db
def test_edit_refuses_an_alias_that_is_a_unit_or_another_units_alias(staff_client):
    """A spelling means one unit only; nothing is written."""
    cup = _unit("cup")
    for aliases, message in (("tsp", "already a unit"), ("tablespoon", "already means tbsp")):
        response = staff_client.post(
            f"{MANAGE}{cup.pk}/save/",
            {"name": "cup", "dimension": "volume", "aliases": aliases},
        )
        assert response.status_code == 422
        assert message in response.content.decode()
    assert not UnitAlias.objects.filter(unit=cup).exists()


@pytest.mark.django_db
def test_edit_refuses_a_name_that_is_another_units_alias(staff_client):
    """A name is a unit or an alias, never both."""
    cup = _unit("cup")
    response = staff_client.post(
        f"{MANAGE}{cup.pk}/save/", {"name": "Tablespoon", "dimension": "volume"}
    )
    assert response.status_code == 422
    assert "already means tbsp" in response.content.decode()


@pytest.mark.django_db
def test_edit_refuses_a_name_its_owner_already_has(staff_client, user, private_unit):
    """A private unit's name is unique within its owner's units."""
    private_unit("punnet", owner=user)
    unit = private_unit("punet", owner=user)
    response = staff_client.post(f"{MANAGE}{unit.pk}/save/", {"name": "Punnet", "dimension": ""})
    assert response.status_code == 422
    assert "Its owner already has that unit." in response.content.decode()


@pytest.mark.django_db
def test_edit_keeps_a_private_unit_private_and_offers_no_aliases(staff_client, user, private_unit):
    """Fixing a user's typo leaves it theirs; aliases are for global units only."""
    unit = private_unit("punet", owner=user)
    html = staff_client.get(MANAGE + "edit/", {"unit_ids": [unit.pk]}).content.decode()
    assert 'name="aliases"' not in html
    staff_client.post(f"{MANAGE}{unit.pk}/save/", {"name": "punnet", "dimension": ""})
    unit.refresh_from_db()
    assert (unit.name, unit.owner) == ("punnet", user)


# --- Promote -----------------------------------------------------------------------


@pytest.mark.django_db
def test_promote_makes_a_private_unit_global_and_folds_in_the_same_name(
    user, other_user, private_unit, row_with
):
    """Everyone's `punnet` becomes the one global unit, and their rows follow."""
    mine = private_unit("punnet", owner=user)
    theirs = private_unit("Punnet", owner=other_user)
    their_row = row_with(theirs, owner=other_user)
    assert promote_units([mine.pk], dimension=Unit.COUNT) == [mine.pk]
    mine.refresh_from_db()
    assert (mine.owner, mine.dimension) == (None, Unit.COUNT)
    assert not Unit.objects.filter(pk=theirs.pk).exists()
    their_row.refresh_from_db()
    assert their_row.unit == mine


@pytest.mark.django_db
def test_promote_merges_into_an_existing_global_unit(user, private_unit, row_with):
    """A private `Cup` becomes the global `cup`."""
    private = private_unit("Cup", owner=user)
    row = row_with(private, owner=user)
    assert promote_units([private.pk], dimension="") == [_unit("cup").pk]
    row.refresh_from_db()
    assert row.unit == _unit("cup")


@pytest.mark.django_db
def test_promote_needs_a_dimension_for_a_new_global_unit(user, private_unit):
    """Nothing is written without one."""
    unit = private_unit("punnet", owner=user)
    with pytest.raises(ValueError, match="dimension"):
        promote_units([unit.pk], dimension="")
    unit.refresh_from_db()
    assert unit.owner == user


@pytest.mark.django_db
def test_promote_route(staff_client, user, private_unit):
    """GET asks for the dimension; POST promotes and keeps the result selected."""
    unit = private_unit("punnet", owner=user)
    asked = staff_client.get(MANAGE + "promote/", {"unit_ids": [unit.pk]}).content.decode()
    assert 'name="dimension"' in asked
    missing = staff_client.post(MANAGE + "promote/", {"unit_ids": [unit.pk], "dimension": ""})
    assert missing.status_code == 422
    done = staff_client.post(MANAGE + "promote/", {"unit_ids": [unit.pk], "dimension": "count"})
    assert done.status_code == 200
    assert _checked(done.content.decode(), unit)
    unit.refresh_from_db()
    assert unit.owner is None


# --- Merge -------------------------------------------------------------------------


@pytest.mark.django_db
def test_merge_moves_every_users_rows_and_keeps_the_names_as_aliases(
    user, other_user, private_unit, row_with
):
    """`tbls` merged into `tbsp` becomes a spelling of it."""
    typo = private_unit("tbls", owner=other_user)
    row = row_with(typo, owner=other_user)
    assert merge_units(survivor_id=_unit("tbsp").pk, victim_ids=[typo.pk], keep_aliases=True) == 1
    row.refresh_from_db()
    assert row.unit == _unit("tbsp")
    assert UnitAlias.objects.get(alias_name="tbls").unit == _unit("tbsp")


@pytest.mark.django_db
def test_merge_moves_a_global_victims_aliases(row_with, user):
    """The victim's own spellings now mean the survivor."""
    tsp = _unit("tsp")
    UnitAlias.objects.create(alias_name="teaspoonful", unit=tsp)
    merge_units(survivor_id=_unit("tbsp").pk, victim_ids=[tsp.pk], keep_aliases=False)
    assert UnitAlias.objects.get(alias_name="teaspoonful").unit == _unit("tbsp")
    assert not UnitAlias.objects.filter(alias_name="tsp").exists()


@pytest.mark.django_db
def test_merge_into_a_private_unit_stays_within_its_owner(user, other_user, private_unit, row_with):
    """A private unit may not land in another user's recipe; nothing is written."""
    mine = private_unit("punnet", owner=user)
    theirs = private_unit("basket", owner=other_user)
    row = row_with(theirs, owner=other_user)
    with pytest.raises(UnitScopeError):
        merge_units(survivor_id=mine.pk, victim_ids=[theirs.pk], keep_aliases=True)
    row.refresh_from_db()
    assert row.unit == theirs


@pytest.mark.django_db
def test_merge_route(staff_client, user, private_unit, row_with):
    """GET offers the selection as survivors; POST merges."""
    typo = private_unit("tbls", owner=user)
    tbsp = _unit("tbsp")
    asked = staff_client.get(MANAGE + "merge/", {"unit_ids": [tbsp.pk, typo.pk]}).content.decode()
    assert 'name="survivor_id"' in asked
    assert 'name="keep_aliases"' in asked
    response = staff_client.post(
        MANAGE + "merge/",
        {"unit_ids": [tbsp.pk, typo.pk], "survivor_id": tbsp.pk, "keep_aliases": "1"},
    )
    assert response.status_code == 200
    assert not Unit.objects.filter(pk=typo.pk).exists()


@pytest.mark.django_db
def test_merge_route_needs_two_and_a_survivor(staff_client, user, private_unit):
    """The guard and a missing survivor are 422."""
    one = staff_client.get(MANAGE + "merge/", {"unit_ids": [_unit("cup").pk]})
    assert one.status_code == 422
    two = [_unit("cup").pk, _unit("tsp").pk]
    missing = staff_client.post(MANAGE + "merge/", {"unit_ids": two})
    assert missing.status_code == 422
    assert "Pick which unit to keep." in missing.content.decode()


# --- Delete ------------------------------------------------------------------------


@pytest.mark.django_db
def test_delete_moves_rows_to_the_replacement(user, private_unit, row_with):
    """Every user's rows move, and the unit goes."""
    typo = private_unit("tbls", owner=user)
    row = row_with(typo, owner=user)
    assert delete_units(unit_ids=[typo.pk], replacement_id=_unit("tbsp").pk) == 1
    row.refresh_from_db()
    assert row.unit == _unit("tbsp")


@pytest.mark.django_db
def test_delete_without_a_replacement_keeps_the_name_as_text(user, private_unit, row_with):
    """Nothing is lost: the row shows the unit as written until it is fixed."""
    unit = private_unit("punnet", owner=user)
    row = row_with(unit, owner=user)
    delete_units(unit_ids=[unit.pk])
    row.refresh_from_db()
    assert (row.unit, row.legacy_unit) == (None, "punnet")
    assert not Unit.objects.filter(pk=unit.pk).exists()


@pytest.mark.django_db
def test_delete_refuses_a_private_replacement_for_another_users_rows(
    user, other_user, private_unit, row_with
):
    """The same scope rule as merge."""
    theirs = private_unit("basket", owner=other_user)
    row_with(theirs, owner=other_user)
    with pytest.raises(UnitScopeError):
        delete_units(unit_ids=[theirs.pk], replacement_id=private_unit("punnet", owner=user).pk)
    assert Unit.objects.filter(pk=theirs.pk).exists()


@pytest.mark.django_db
def test_delete_route_counts_every_users_rows(
    staff_client, user, other_user, private_unit, row_with
):
    """The confirmation warns about rows across every user; POST deletes."""
    unit = private_unit("punnet", owner=other_user)
    row_with(unit, owner=other_user)
    asked = staff_client.get(MANAGE + "delete/", {"unit_ids": [unit.pk]}).content.decode()
    assert "Used in 1 ingredient row, across every user." in asked
    response = staff_client.post(
        MANAGE + "delete/", {"unit_ids": [unit.pk], "replacement_id": _unit("cup").pk}
    )
    assert response.status_code == 200
    assert not Unit.objects.filter(pk=unit.pk).exists()


@pytest.mark.django_db
def test_delete_route_answers_a_scope_error(staff_client, user, other_user, private_unit, row_with):
    """A refused delete is 422 with the reason."""
    theirs = private_unit("basket", owner=other_user)
    row_with(theirs, owner=other_user)
    mine = private_unit("punnet", owner=user)
    response = staff_client.post(
        MANAGE + "delete/", {"unit_ids": [theirs.pk], "replacement_id": mine.pk}
    )
    assert response.status_code == 422
    assert "promote it first" in response.content.decode()
