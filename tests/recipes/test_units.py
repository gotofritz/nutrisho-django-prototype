"""Tests for the canonical unit vocabulary and resolving typed units (#67)."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from recipes.models import Ingredient, IngredientInRecipe, Unit, UnitAlias
from recipes.services.name_resolution import find_unit, unit_names
from recipes.templatetags.recipe_filters import display_ingredient_name, display_unit, unit_at

# --- the vocabulary -----------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "dimension"),
    [
        ("g", Unit.MASS),
        ("kg", Unit.MASS),
        ("ml", Unit.VOLUME),
        ("l", Unit.VOLUME),
        ("tsp", Unit.VOLUME),
        ("tbsp", Unit.VOLUME),
        ("cup", Unit.VOLUME),
        ("clove", Unit.COUNT),
        ("sprig", Unit.COUNT),
        ("pinch", Unit.COUNT),
    ],
)
def test_the_vocabulary_is_seeded_with_a_dimension(name, dimension):
    """The migration seeds the common units, each with mass, volume or count."""
    assert Unit.objects.get(name=name).dimension == dimension


@pytest.mark.django_db
def test_unit_names_are_unique_ignoring_case():
    """`l` and `L` are one unit."""
    with pytest.raises(IntegrityError):
        Unit.objects.create(name="L", dimension=Unit.VOLUME)


@pytest.mark.django_db
def test_alias_names_are_unique_ignoring_case():
    """An alias means one unit only."""
    with pytest.raises(IntegrityError):
        UnitAlias.objects.create(alias_name="TABLESPOON", unit=Unit.objects.get(name="tsp"))


@pytest.mark.django_db
def test_an_alias_may_not_be_a_unit_name():
    """A name is a unit or an alias, never both."""
    alias = UnitAlias(alias_name=" Cup ", unit=Unit.objects.get(name="tbsp"))
    with pytest.raises(ValidationError, match="already a unit"):
        alias.full_clean()


@pytest.mark.django_db
def test_an_alias_clean_strips_the_name():
    """Surrounding space is not part of an alias."""
    alias = UnitAlias(alias_name="  tbso ", unit=Unit.objects.get(name="tbsp"))
    alias.full_clean()
    assert alias.alias_name == "tbso"


@pytest.mark.django_db
def test_deleting_a_unit_deletes_its_aliases():
    """Aliases cascade with their unit."""
    unit = Unit.objects.create(name="bushel", dimension=Unit.VOLUME)
    UnitAlias.objects.create(alias_name="bu", unit=unit)
    unit.delete()
    assert not UnitAlias.objects.filter(alias_name="bu").exists()


@pytest.mark.django_db
def test_a_used_unit_cannot_be_deleted(user, make_recipe, add_ingredient, make_ingredient):
    """Recipes point at units with PROTECT, like ingredients."""
    from django.db.models import ProtectedError

    unit = Unit.objects.create(name="bushel", dimension=Unit.VOLUME)
    add_ingredient(
        recipe=make_recipe(owner=user, name="Harvest"),
        ingredient=make_ingredient("apple"),
        quantity=Decimal(1),
        unit="bushel",
    )
    with pytest.raises(ProtectedError):
        unit.delete()


@pytest.mark.django_db
def test_unit_plural_follows_the_rule_or_the_override():
    """`cup` inflects; an abbreviation is invariant through its override."""
    assert Unit.objects.get(name="cup").plural == "cups"
    assert Unit.objects.get(name="clove").plural == "cloves"
    assert Unit.objects.get(name="g").plural == "g"
    assert Unit.objects.get(name="tbsp").plural == "tbsp"
    assert str(Unit.objects.get(name="tbsp")) == "tbsp"
    assert str(UnitAlias.objects.get(alias_name="tablespoon")) == "tablespoon → tbsp"


# --- resolving what was typed -------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("typed", "canonical"),
    [
        ("tbsp", "tbsp"),
        ("Tbsp", "tbsp"),
        (" TBSP ", "tbsp"),
        ("tbsp.", "tbsp"),
        ("tbs", "tbsp"),
        ("tablespoon", "tbsp"),
        ("tablespoons", "tbsp"),
        ("L", "l"),
        ("litre", "l"),
        ("cloves", "clove"),
        ("cups", "cup"),
        ("sprigs", "sprig"),
        ("grams", "g"),
        ("pcs", "piece"),
        ("can", "tin"),
    ],
)
def test_find_unit_resolves_case_plurals_and_aliases(typed, canonical):
    """Spellings of the same unit resolve to its one canonical row."""
    assert find_unit(typed) == Unit.objects.get(name=canonical)


@pytest.mark.django_db
@pytest.mark.parametrize("typed", ["", "  ", "tbso", "small", "to taste", "t%p"])
def test_find_unit_misses_unknown_text(typed):
    """A typo or a word that is not a unit resolves to nothing, and nothing is created."""
    before = Unit.objects.count()
    assert find_unit(typed) is None
    assert Unit.objects.count() == before


@pytest.mark.django_db
def test_find_unit_uses_an_alias_staff_added():
    """An alias added in admin resolves from then on."""
    UnitAlias.objects.create(alias_name="tbso", unit=Unit.objects.get(name="tbsp"))
    assert find_unit("Tbso") == Unit.objects.get(name="tbsp")


@pytest.mark.django_db
def test_unit_names_lists_canonical_names_for_the_editor():
    """The editor suggests canonical names only, sorted ignoring case."""
    names = unit_names()
    assert "tbsp" in names
    assert "tablespoon" not in names
    assert names == sorted(names, key=str.lower)


# --- display -------------------------------------------------------------------


def _iir(
    quantity: Decimal | None, *, unit: Unit | None = None, legacy: str = ""
) -> IngredientInRecipe:
    return IngredientInRecipe(
        ingredient=Ingredient(ingredient_name="garlic"),
        quantity=quantity,
        unit=unit,
        legacy_unit=legacy,
    )


def test_unit_is_singular_at_one_and_without_a_quantity():
    """`1 clove`, and a bare `pinch` with no number."""
    clove = Unit(name="clove", dimension=Unit.COUNT)
    assert display_unit(_iir(Decimal(1), unit=clove)) == "clove"
    assert display_unit(_iir(None, unit=clove)) == "clove"


def test_unit_is_plural_at_any_other_quantity():
    """`2 cloves` and `0.5 cups` come from one stored singular."""
    assert display_unit(_iir(Decimal(2), unit=Unit(name="clove", dimension=Unit.COUNT))) == "cloves"
    assert (
        display_unit(_iir(Decimal("0.5"), unit=Unit(name="cup", dimension=Unit.VOLUME))) == "cups"
    )


def test_an_invariant_unit_stays_as_it_is():
    """`200 g`, never `200 gs`."""
    gram = Unit(name="g", plural_name="g", dimension=Unit.MASS)
    assert display_unit(_iir(Decimal(200), unit=gram)) == "g"


def test_unit_follows_the_displayed_quantity_when_scaled():
    """1 clove doubled reads `2 cloves`."""
    clove = Unit(name="clove", dimension=Unit.COUNT)
    assert unit_at(_iir(Decimal(1), unit=clove), Decimal(2)) == "cloves"
    assert unit_at(_iir(Decimal(2), unit=clove), Decimal(1)) == "clove"


def test_a_legacy_unit_shows_as_stored_until_it_is_cleaned_up():
    """Unreviewed text is shown verbatim, not pluralised."""
    assert display_unit(_iir(Decimal(2), legacy="Tbsp")) == "Tbsp"
    assert display_unit(_iir(Decimal(2))) == ""


def test_a_legacy_unit_still_keeps_the_ingredient_singular():
    """`2 Tbsp garlic`, as before the vocabulary."""
    assert display_ingredient_name(_iir(Decimal(2), legacy="Tbsp")) == "garlic"


def test_a_unit_keeps_the_ingredient_singular():
    """`2 cloves garlic`, never `2 cloves garlics`."""
    clove = Unit(name="clove", dimension=Unit.COUNT)
    assert display_ingredient_name(_iir(Decimal(2), unit=clove)) == "garlic"


@pytest.mark.django_db
def test_recipe_page_pluralises_the_unit(
    auth_client, user, make_recipe, add_ingredient, make_ingredient
):
    """The page shows `2 cloves garlic` and, scaled down, `1 clove garlic`."""
    recipe = make_recipe(owner=user, name="Aioli")
    add_ingredient(
        recipe=recipe, ingredient=make_ingredient("garlic"), quantity=Decimal(2), unit="clove"
    )
    content = auth_client.get(f"/recipes/{recipe.pk}/").content.decode()
    assert '<span class="ingredient-unit">cloves</span>' in content
    scaled = auth_client.get(f"/recipes/{recipe.pk}/?servings=2").content.decode()
    assert '<span class="ingredient-unit">clove</span>' in scaled


# --- the editor ------------------------------------------------------------------


@pytest.fixture
def garlic_row(user, make_recipe, add_ingredient, make_ingredient):
    """A recipe with one `2 clove garlic` row."""
    recipe = make_recipe(owner=user, name="Aioli")
    row = add_ingredient(
        recipe=recipe, ingredient=make_ingredient("garlic"), quantity=Decimal(2), unit="clove"
    )
    return recipe, row


def _save(auth_client, recipe, row, unit: str, **extra: str):
    data = {
        "ingredient_name": "garlic",
        "quantity": "2",
        "unit": unit,
        "preparation": "",
        "note": "",
    }
    data.update(extra)
    return auth_client.post(f"/recipes/{recipe.pk}/ingredients/{row.pk}/save/", data)


@pytest.mark.django_db
def test_editor_stores_the_canonical_unit_for_a_variant(auth_client, garlic_row):
    """Typing `Tablespoons` stores `tbsp`, with no error."""
    recipe, row = garlic_row
    response = _save(auth_client, recipe, row, "Tablespoons")
    assert "<form" not in response.content.decode()
    row.refresh_from_db()
    assert row.unit == Unit.objects.get(name="tbsp")
    assert row.legacy_unit == ""


@pytest.mark.django_db
def test_editor_clears_the_unit_when_left_blank(auth_client, garlic_row):
    """A blank unit stores none."""
    recipe, row = garlic_row
    _save(auth_client, recipe, row, "  ")
    row.refresh_from_db()
    assert row.unit is None


@pytest.mark.django_db
def test_editor_refuses_an_unknown_unit_and_writes_nothing(auth_client, garlic_row):
    """An unknown unit is an error on the field, not a new unit."""
    recipe, row = garlic_row
    before = Unit.objects.count()
    response = _save(auth_client, recipe, row, "tbso", quantity="5")
    content = response.content.decode()
    assert "<form" in content
    assert "is not a unit" in content
    row.refresh_from_db()
    assert row.quantity == 2
    assert Unit.objects.count() == before


@pytest.mark.django_db
def test_editor_sends_a_size_word_to_preparation(auth_client, garlic_row):
    """`small` is refused with a pointer to the field it belongs in."""
    recipe, row = garlic_row
    content = _save(auth_client, recipe, row, "small").content.decode()
    assert "<form" in content
    assert "put it under preparation" in content


@pytest.mark.django_db
def test_editor_sends_to_taste_to_the_note(auth_client, garlic_row):
    """`to taste` is refused with a pointer to the note."""
    recipe, row = garlic_row
    content = _save(auth_client, recipe, row, "to taste").content.decode()
    assert "put it under note" in content


@pytest.mark.django_db
def test_editor_prefills_the_unit_and_offers_the_vocabulary(auth_client, garlic_row):
    """The edit form shows the canonical unit and suggests the others."""
    recipe, row = garlic_row
    content = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{row.pk}/edit/").content.decode()
    assert 'name="unit" value="clove"' in content
    assert 'list="units-datalist"' in content
    assert '<option value="tbsp">' in content


@pytest.mark.django_db
def test_editor_prefills_a_legacy_unit_and_saving_resolves_it(auth_client, garlic_row):
    """An uncleaned row shows its text; saving it stores the canonical unit."""
    recipe, row = garlic_row
    IngredientInRecipe.objects.filter(pk=row.pk).update(unit=None, legacy_unit="Tbsp")
    content = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{row.pk}/edit/").content.decode()
    assert 'name="unit" value="Tbsp"' in content
    _save(auth_client, recipe, row, "Tbsp")
    row.refresh_from_db()
    assert row.unit == Unit.objects.get(name="tbsp")
    assert row.legacy_unit == ""


@pytest.mark.django_db
def test_editor_create_resolves_the_unit(auth_client, garlic_row):
    """A new row resolves its unit too."""
    recipe, row = garlic_row
    response = auth_client.post(
        f"/recipes/{recipe.pk}/groups/{row.ingredient_group_id}/ingredients/create/",
        {"ingredient_name": "oil", "quantity": "2", "unit": "Tbsp", "preparation": "", "note": ""},
    )
    assert '<span class="ingredient-unit">tbsp</span>' in response.content.decode()
    created = IngredientInRecipe.objects.get(ingredient__ingredient_name="oil")
    assert created.unit == Unit.objects.get(name="tbsp")
