"""Undo for the ingredient clean-up tool's merges and deletes (#75).

Every change that deletes ingredients writes an `IngredientChange` recording
what it deleted, which recipe rows and aliases it repointed, and what else it
changed, so the most recent change can be put back exactly.
"""

import re

import pytest
from django.test import Client

from recipes.models import Ingredient, IngredientAlias, IngredientChange, IngredientInRecipe
from recipes.services.ingredient_admin import (
    IngredientInUseError,
    add_alias,
    delete_ingredients,
    merge_ingredients,
    merge_plural_ingredients,
    promote_ingredients,
)
from recipes.services.ingredient_journal import (
    UndoError,
    journaled,
    recent_changes,
    undo_change,
)

MANAGE = "/recipes/ingredients/manage/"
UNDO_URL = MANAGE + "undo/"


@pytest.fixture
def staff(user):
    """The default user, made staff."""
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


@pytest.fixture
def staff_client(staff):
    """A staff client."""
    c = Client()
    c.force_login(staff)
    return c


@pytest.fixture
def soup(user, make_recipe):
    """A recipe to hang ingredient rows on."""
    return make_recipe(owner=user, name="Soup")


def _snapshot() -> dict[str, list]:
    """Every ingredient, alias and recipe row's references, for before/after comparisons."""
    return {
        "ingredients": list(
            Ingredient.objects.order_by("pk").values_list(
                "pk", "ingredient_name", "plural_name", "owner_id", "family"
            )
        ),
        "aliases": list(
            IngredientAlias.objects.order_by("pk").values_list("pk", "alias_name", "canonical_id")
        ),
        "rows": list(
            IngredientInRecipe.objects.order_by("pk").values_list(
                "pk", "ingredient_id", "substitute_id"
            )
        ),
    }


# --- Services ---


@pytest.mark.django_db
def test_undo_merge_puts_everything_back(staff, soup, make_ingredient, add_ingredient):
    """Victims, their recipe rows, substitutes and aliases return exactly."""
    onion = make_ingredient("onion")
    shallot = make_ingredient("shallot")
    shallot.family = "VEG"
    shallot.save()
    leek = make_ingredient("leek")
    add_ingredient(recipe=soup, ingredient=shallot, substitute=leek)
    add_ingredient(recipe=soup, ingredient=leek, substitute=shallot)
    add_ingredient(recipe=soup, ingredient=onion)
    IngredientAlias.objects.create(alias_name="echalote", canonical=shallot)
    before = _snapshot()

    with journaled(user=staff) as journal:
        merge_ingredients(
            survivor_id=onion.pk, victim_ids=[onion.pk, shallot.pk, leek.pk], journal=journal
        )
    assert _snapshot() != before

    change = IngredientChange.objects.get()
    restored = undo_change(change_id=change.pk)

    assert _snapshot() == before
    assert sorted(restored) == sorted([shallot.pk, leek.pk])
    change.refresh_from_db()
    assert change.undone_at is not None


@pytest.mark.django_db
def test_undo_delete_with_replacement(staff, soup, make_ingredient, add_ingredient):
    """A delete that moved recipes onto a replacement moves them back."""
    onion = make_ingredient("onion")
    onions = make_ingredient("onions")
    add_ingredient(recipe=soup, ingredient=onions)
    before = _snapshot()
    with journaled(user=staff) as journal:
        delete_ingredients(ingredient_ids=[onions.pk], replacement_id=onion.pk, journal=journal)
    undo_change(change_id=IngredientChange.objects.get().pk)
    assert _snapshot() == before


@pytest.mark.django_db
def test_undo_delete_of_unused_ingredient(staff, make_ingredient):
    """An outright delete comes back with its id."""
    gone = make_ingredient("dragonfruit")
    before = _snapshot()
    with journaled(user=staff) as journal:
        delete_ingredients(ingredient_ids=[gone.pk], journal=journal)
    undo_change(change_id=IngredientChange.objects.get().pk)
    assert _snapshot() == before


@pytest.mark.django_db
def test_undo_merge_plural_restores_the_old_plural(staff, soup, make_ingredient, add_ingredient):
    """The singular's plural_name goes back to what it was."""
    chili = make_ingredient("chili", plural_name="chilies")
    chilis = make_ingredient("chilis")
    add_ingredient(recipe=soup, ingredient=chilis)
    before = _snapshot()
    with journaled(user=staff) as journal:
        merge_plural_ingredients(singular_id=chili.pk, plural_id=chilis.pk, journal=journal)
    undo_change(change_id=IngredientChange.objects.get().pk)
    assert _snapshot() == before


@pytest.mark.django_db
def test_undo_promote_makes_the_row_private_again(
    staff, other_user, soup, make_ingredient, add_ingredient
):
    """Promote's owner change and its fold-in of other users' rows are reversed."""
    mine = Ingredient.objects.create(ingredient_name="yuzu kosho", owner=staff)
    theirs = Ingredient.objects.create(ingredient_name="Yuzu Kosho", owner=other_user)
    add_ingredient(recipe=soup, ingredient=mine)
    before = _snapshot()
    with journaled(user=staff) as journal:
        promote_ingredients([mine.pk], journal=journal)
    assert not Ingredient.objects.filter(pk=theirs.pk).exists()
    undo_change(change_id=IngredientChange.objects.get().pk)
    assert _snapshot() == before


@pytest.mark.django_db
def test_undo_alias_removes_it_and_brings_back_what_it_folded_in(staff, make_ingredient):
    """An alias that merged rows of its name undoes both."""
    aubergine = make_ingredient("aubergine")
    make_ingredient("eggplant")
    before = _snapshot()
    with journaled(user=staff) as journal:
        add_alias(canonical_id=aubergine.pk, alias_name="eggplant", journal=journal)
    undo_change(change_id=IngredientChange.objects.get().pk)
    assert _snapshot() == before


@pytest.mark.django_db
def test_journal_records_nothing_when_nothing_changed(staff, make_ingredient):
    """A no-op writes no history entry."""
    with journaled(user=staff) as journal:
        delete_ingredients(ingredient_ids=[], journal=journal)
    assert not IngredientChange.objects.exists()


@pytest.mark.django_db
def test_failed_change_records_nothing(staff, soup, make_ingredient, add_ingredient):
    """A change that raises rolls back its entry with it."""
    onion = make_ingredient("onion")
    add_ingredient(recipe=soup, ingredient=onion)
    with pytest.raises(IngredientInUseError), journaled(user=staff) as journal:
        delete_ingredients(ingredient_ids=[onion.pk], journal=journal)
    assert not IngredientChange.objects.exists()


@pytest.mark.django_db
def test_journal_describes_the_change(staff, make_ingredient):
    """The entry says what happened, by name."""
    onion = make_ingredient("onion")
    shallot = make_ingredient("shallot")
    with journaled(user=staff) as journal:
        merge_ingredients(survivor_id=onion.pk, victim_ids=[onion.pk, shallot.pk], journal=journal)
    change = IngredientChange.objects.get()
    assert change.summary == "Merged “shallot” into “onion”"
    assert change.user == staff


@pytest.mark.django_db
def test_only_the_latest_change_can_be_undone(staff, make_ingredient):
    """Undo goes back one change at a time, newest first."""
    for name in ("fig", "date"):
        with journaled(user=staff) as journal:
            delete_ingredients(ingredient_ids=[make_ingredient(name).pk], journal=journal)
    older, newer = IngredientChange.objects.order_by("pk")
    with pytest.raises(UndoError):
        undo_change(change_id=older.pk)
    undo_change(change_id=newer.pk)
    undo_change(change_id=older.pk)
    assert set(Ingredient.objects.values_list("ingredient_name", flat=True)) == {"fig", "date"}


@pytest.mark.django_db
def test_undo_twice_is_refused(staff, make_ingredient):
    """An undone change cannot be undone again."""
    with journaled(user=staff) as journal:
        delete_ingredients(ingredient_ids=[make_ingredient("fig").pk], journal=journal)
    change = IngredientChange.objects.get()
    undo_change(change_id=change.pk)
    with pytest.raises(UndoError):
        undo_change(change_id=change.pk)


@pytest.mark.django_db
def test_undo_refuses_when_the_name_is_taken_again(staff, make_ingredient):
    """A new row with a deleted name blocks the undo; nothing is written."""
    with journaled(user=staff) as journal:
        delete_ingredients(ingredient_ids=[make_ingredient("fig").pk], journal=journal)
    make_ingredient("Fig")
    change = IngredientChange.objects.get()
    with pytest.raises(UndoError, match="“fig”"):
        undo_change(change_id=change.pk)
    change.refresh_from_db()
    assert change.undone_at is None
    assert list(Ingredient.objects.values_list("ingredient_name", flat=True)) == ["Fig"]


@pytest.mark.django_db
def test_undo_leaves_rows_edited_since_alone(staff, soup, make_ingredient, add_ingredient):
    """A recipe row moved to another ingredient after the merge keeps its new one."""
    onion = make_ingredient("onion")
    shallot = make_ingredient("shallot")
    garlic = make_ingredient("garlic")
    row = add_ingredient(recipe=soup, ingredient=shallot)
    with journaled(user=staff) as journal:
        merge_ingredients(survivor_id=onion.pk, victim_ids=[onion.pk, shallot.pk], journal=journal)
    IngredientInRecipe.objects.filter(pk=row.pk).update(ingredient=garlic)
    undo_change(change_id=IngredientChange.objects.get().pk)
    row.refresh_from_db()
    assert row.ingredient_id == garlic.pk
    assert Ingredient.objects.filter(pk=shallot.pk).exists()


@pytest.mark.django_db
def test_recent_changes_newest_first(staff, make_ingredient):
    """The history lists the newest change first."""
    for name in ("fig", "date"):
        with journaled(user=staff) as journal:
            delete_ingredients(ingredient_ids=[make_ingredient(name).pk], journal=journal)
    assert [c.summary for c in recent_changes()] == ["Deleted “date”", "Deleted “fig”"]


# --- Views ---


@pytest.mark.django_db
def test_merge_view_records_a_change(staff_client, make_ingredient):
    """Merging in the tool writes a history entry."""
    onion = make_ingredient("onion")
    shallot = make_ingredient("shallot")
    staff_client.post(
        MANAGE + "merge/", {"ingredient_ids": [onion.pk, shallot.pk], "survivor_id": onion.pk}
    )
    assert IngredientChange.objects.get().summary == "Merged “shallot” into “onion”"


@pytest.mark.django_db
def test_delete_view_records_a_change(staff_client, make_ingredient):
    """Deleting in the tool writes a history entry."""
    fig = make_ingredient("fig")
    staff_client.post(MANAGE + "delete/", {"ingredient_ids": [fig.pk]})
    assert IngredientChange.objects.get().summary == "Deleted “fig”"


@pytest.mark.django_db
def test_merge_plural_promote_and_alias_views_record_changes(staff_client, staff, make_ingredient):
    """Every action that deletes ingredients can be undone."""
    chili = make_ingredient("chili")
    chilis = make_ingredient("chilis")
    staff_client.post(
        MANAGE + "merge-plural/",
        {"ingredient_ids": [chili.pk, chilis.pk], "singular_id": chili.pk},
    )
    private = Ingredient.objects.create(ingredient_name="sumac", owner=staff)
    staff_client.post(MANAGE + "promote/", {"ingredient_ids": [private.pk]})
    aubergine = make_ingredient("aubergine")
    staff_client.post(
        MANAGE + "alias/", {"ingredient_ids": [aubergine.pk], "alias_name": "eggplant"}
    )
    assert IngredientChange.objects.count() == 3


@pytest.mark.django_db
def test_manager_shows_the_latest_change_with_undo(staff_client, make_ingredient):
    """The tool lists recent changes and offers Undo on the newest."""
    fig = make_ingredient("fig")
    response = staff_client.post(MANAGE + "delete/", {"ingredient_ids": [fig.pk]})
    html = response.content.decode()
    assert 'id="ingredient-changes"' in html
    assert "Deleted “fig”" in html
    assert 'hx-post="/recipes/ingredients/manage/undo/"' in html
    page = staff_client.get(MANAGE).content.decode()
    assert "Deleted “fig”" in page
    assert ">Undo</button>" in page


@pytest.mark.django_db
def test_undo_view_restores_and_selects_the_ingredients(staff_client, make_ingredient):
    """Undo brings the rows back, ticked."""
    fig = make_ingredient("fig")
    staff_client.post(MANAGE + "delete/", {"ingredient_ids": [fig.pk]})
    change = IngredientChange.objects.get()
    response = staff_client.post(UNDO_URL, {"change_id": change.pk})
    assert response.status_code == 200
    assert Ingredient.objects.filter(pk=fig.pk).exists()
    assert f'value="{fig.pk}" checked' in re.sub(r"\s+", " ", response.content.decode())


@pytest.mark.django_db
def test_undo_view_reports_a_refusal(staff_client, make_ingredient):
    """A refused undo comes back as 422 with the reason, and writes nothing."""
    fig = make_ingredient("fig")
    staff_client.post(MANAGE + "delete/", {"ingredient_ids": [fig.pk]})
    make_ingredient("fig")
    change = IngredientChange.objects.get()
    response = staff_client.post(UNDO_URL, {"change_id": change.pk})
    assert response.status_code == 422
    assert "fig" in response.content.decode()
    change.refresh_from_db()
    assert change.undone_at is None


@pytest.mark.django_db
def test_undo_view_rejects_junk(staff_client):
    """A missing or junk id is a 422."""
    assert staff_client.post(UNDO_URL, {"change_id": "x"}).status_code == 422


@pytest.mark.django_db
def test_undo_view_is_staff_only(other_user, staff_client, make_ingredient):
    """A non-staff user is refused and nothing is written."""
    fig = make_ingredient("fig")
    staff_client.post(MANAGE + "delete/", {"ingredient_ids": [fig.pk]})
    change = IngredientChange.objects.get()
    client = Client()
    client.force_login(other_user)
    response = client.post(UNDO_URL, {"change_id": change.pk}, HTTP_HX_REQUEST="true")
    assert response.status_code == 403
    assert not Ingredient.objects.filter(pk=fig.pk).exists()
    change.refresh_from_db()
    assert change.undone_at is None
