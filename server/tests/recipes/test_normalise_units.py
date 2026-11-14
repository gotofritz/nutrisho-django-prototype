"""Tests for moving legacy free-text units onto the vocabulary (#67)."""

from decimal import Decimal

import pytest
from django.core.management import call_command

from recipes.models import IngredientInRecipe, Unit, UnitAlias
from recipes.services.unit_normalisation import apply_unit_plan, plan_unit_normalisation


@pytest.fixture
def legacy_row(user, make_recipe, add_ingredient, make_ingredient):
    """Make a row whose unit is still the free text typed before #67."""
    recipe = make_recipe(owner=user, name="Legacy")
    counter = iter(range(1000))

    def _make(
        legacy: str, *, quantity: str | None = "1", preparation: str = "", note: str = ""
    ) -> IngredientInRecipe:
        row = add_ingredient(
            recipe=recipe,
            ingredient=make_ingredient(f"ingredient-{next(counter)}"),
            quantity=Decimal(quantity) if quantity else None,
        )
        row.legacy_unit = legacy
        row.preparation = preparation
        row.note = note
        row.save()
        return row

    return _make


@pytest.mark.django_db
def test_plan_groups_rows_by_value_and_names_each_action(legacy_row):
    """One line per distinct value: what it becomes and how many rows it touches."""
    for value in ("Tbsp", "Tbsp", "tbsp", "small", "to taste", "tbso"):
        legacy_row(value)
    plan = {entry.value: entry for entry in plan_unit_normalisation()}
    assert set(plan) == {"Tbsp", "tbsp", "small", "to taste", "tbso"}
    assert plan["Tbsp"].rows == 2
    assert plan["Tbsp"].unit == Unit.objects.get(name="tbsp")
    assert plan["small"].unit is None
    assert plan["small"].field == "preparation"
    assert plan["to taste"].field == "note"
    assert plan["tbso"].unit is None
    assert plan["tbso"].field is None


@pytest.mark.django_db
def test_rows_already_on_the_vocabulary_are_not_in_the_plan(legacy_row, user, make_recipe):
    """Only rows with legacy text are reviewed."""
    legacy_row("")
    assert plan_unit_normalisation() == []


@pytest.mark.django_db
def test_apply_points_spellings_at_the_canonical_unit(legacy_row):
    """`Tbsp`, `tbs` and `cloves` become FKs and the legacy text is cleared."""
    rows = [legacy_row("Tbsp"), legacy_row("tbs"), legacy_row("cloves", quantity="2")]
    result = apply_unit_plan(plan_unit_normalisation())
    assert result.updated == 3
    for row in rows:
        row.refresh_from_db()
        assert row.legacy_unit == ""
    assert [r.unit.name for r in rows] == ["tbsp", "tbsp", "clove"]
    assert rows[2].quantity == 2


@pytest.mark.django_db
def test_apply_moves_a_size_word_into_preparation(legacy_row):
    """`2 small onion, chopped` becomes `2 onions, small, chopped`."""
    row = legacy_row("Small", quantity="2", preparation="chopped")
    apply_unit_plan(plan_unit_normalisation())
    row.refresh_from_db()
    assert row.unit is None
    assert row.legacy_unit == ""
    assert row.preparation == "small, chopped"
    assert row.quantity == 2


@pytest.mark.django_db
def test_apply_moves_to_taste_into_the_note_and_drops_the_quantity(legacy_row):
    """A quantity beside `to taste` means nothing, and scaling would multiply it."""
    row = legacy_row("to taste", quantity="1", note="flaky")
    result = apply_unit_plan(plan_unit_normalisation())
    row.refresh_from_db()
    assert row.note == "to taste, flaky"
    assert row.quantity is None
    assert result.quantities_cleared == 1


@pytest.mark.django_db
def test_apply_leaves_unknown_values_for_review(legacy_row):
    """A typo stays as typed, still shown, until staff add an alias or fix it."""
    row = legacy_row("tbso")
    result = apply_unit_plan(plan_unit_normalisation())
    row.refresh_from_db()
    assert row.legacy_unit == "tbso"
    assert result.updated == 0
    UnitAlias.objects.create(alias_name="tbso", unit=Unit.objects.get(name="tbsp"))
    apply_unit_plan(plan_unit_normalisation())
    row.refresh_from_db()
    assert row.unit == Unit.objects.get(name="tbsp")


@pytest.mark.django_db
def test_apply_skips_a_row_whose_field_would_overflow(legacy_row):
    """Never truncate: a preparation with no room left is reported and kept."""
    row = legacy_row("large", preparation="x" * 125)
    result = apply_unit_plan(plan_unit_normalisation())
    row.refresh_from_db()
    assert row.legacy_unit == "large"
    assert result.skipped == [row.pk]


@pytest.mark.django_db
def test_command_is_a_dry_run_by_default(legacy_row, capsys):
    """Without --apply it reports and writes nothing."""
    row = legacy_row("Tbsp")
    legacy_row("tbso")
    call_command("normalise_units")
    out = capsys.readouterr().out
    assert "Tbsp" in out
    assert "→ tbsp" in out
    assert "tbso" in out
    assert "unknown" in out
    assert "--apply" in out
    row.refresh_from_db()
    assert row.legacy_unit == "Tbsp"


@pytest.mark.django_db
def test_command_applies_with_the_flag(legacy_row, capsys):
    """--apply writes the plan and says what it did."""
    row = legacy_row("Tbsp")
    legacy_row("tbso")
    legacy_row("medium", preparation="x" * 125)
    legacy_row("to taste")
    call_command("normalise_units", "--apply")
    out = capsys.readouterr().out
    assert "Updated 2 rows" in out
    assert "1 quantity cleared" in out
    assert "Skipped 1 row" in out
    assert "1 value left" in out
    row.refresh_from_db()
    assert row.unit == Unit.objects.get(name="tbsp")


@pytest.mark.django_db
def test_command_reports_a_clean_database(capsys):
    """Nothing to do is said plainly."""
    call_command("normalise_units")
    assert "No legacy units left" in capsys.readouterr().out
