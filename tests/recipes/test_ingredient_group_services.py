"""Tests for the ingredient group and row services (#77), called without a request."""

import pytest

from recipes.models import IngredientGroup, IngredientInRecipe, Recipe
from recipes.services.ingredient_groups import (
    GroupDeletion,
    ReassignError,
    delete_group,
    delete_row,
    move_row,
    prune_empty_group,
    reassign_rows,
)


@pytest.fixture
def recipe(user, make_recipe) -> Recipe:
    """A recipe owned by the test user."""
    return make_recipe(owner=user, name="Services")


@pytest.fixture
def add_group(recipe):
    """Append a group to `recipe`."""

    def _add(name: str) -> IngredientGroup:
        return IngredientGroup.objects.create(
            recipe=recipe,
            group_name=name,
            index_in_sequence=IngredientGroup.objects.filter(recipe=recipe).count(),
        )

    return _add


@pytest.fixture
def add_row(make_ingredient):
    """Append a row for a new ingredient to `group`."""

    def _add(group: IngredientGroup, name: str) -> IngredientInRecipe:
        return IngredientInRecipe.objects.create(
            ingredient=make_ingredient(name),
            ingredient_group=group,
            index_in_sequence=IngredientInRecipe.objects.filter(ingredient_group=group).count(),
        )

    return _add


def _layout(recipe: Recipe) -> list[tuple[str, list[str]]]:
    """Each group's name and its rows' ingredient names, in page order."""
    return [
        (
            g.group_name,
            [
                r.ingredient.ingredient_name
                for r in IngredientInRecipe.objects.filter(ingredient_group=g).order_by(
                    "index_in_sequence"
                )
            ],
        )
        for g in IngredientGroup.objects.filter(recipe=recipe).order_by("index_in_sequence")
    ]


def _indexes(recipe: Recipe) -> list[int]:
    return list(
        IngredientGroup.objects.filter(recipe=recipe)
        .order_by("index_in_sequence")
        .values_list("index_in_sequence", flat=True)
    )


# --- prune_empty_group ---


@pytest.mark.django_db
def test_prune_drops_an_empty_group_and_compacts(recipe, add_group, add_row):
    """An empty group goes, and the groups after it close the gap."""
    first, empty, last = add_group("A"), add_group("B"), add_group("C")
    add_row(first, "salt")
    add_row(last, "pepper")
    assert prune_empty_group(recipe=recipe, group=empty) is True
    assert _layout(recipe) == [("A", ["salt"]), ("C", ["pepper"])]
    assert _indexes(recipe) == [0, 1]


@pytest.mark.django_db
def test_prune_keeps_a_group_with_rows(recipe, add_group, add_row):
    """A group that still has a row stays."""
    group = add_group("A")
    add_group("B")
    add_row(group, "salt")
    assert prune_empty_group(recipe=recipe, group=group) is False
    assert IngredientGroup.objects.filter(pk=group.pk).exists()


@pytest.mark.django_db
def test_prune_keeps_the_last_group(recipe, add_group):
    """A recipe's only group survives even when empty."""
    group = add_group("A")
    assert prune_empty_group(recipe=recipe, group=group) is False
    assert IngredientGroup.objects.filter(pk=group.pk).exists()


# --- delete_row ---


@pytest.mark.django_db
def test_delete_row_compacts_its_group(recipe, add_group, add_row):
    """The rows after the deleted one move up."""
    group = add_group("A")
    salt, _pepper, _oil = add_row(group, "salt"), add_row(group, "pepper"), add_row(group, "oil")
    deletion = delete_row(recipe=recipe, row_id=salt.pk)
    assert deletion is not None
    assert deletion.group_id == group.pk
    assert deletion.group_pruned is False
    assert list(
        IngredientInRecipe.objects.filter(ingredient_group=group)
        .order_by("index_in_sequence")
        .values_list("index_in_sequence", flat=True)
    ) == [0, 1]


@pytest.mark.django_db
def test_delete_row_prunes_the_group_it_empties(recipe, add_group, add_row):
    """Deleting a group's last row drops the group when another remains."""
    add_row(add_group("A"), "salt")
    second = add_group("B")
    oil = add_row(second, "oil")
    deletion = delete_row(recipe=recipe, row_id=oil.pk)
    assert deletion is not None
    assert deletion.group_id == second.pk
    assert deletion.group_pruned is True
    assert _layout(recipe) == [("A", ["salt"])]


@pytest.mark.django_db
def test_delete_row_of_another_recipe_is_none(recipe, other_user, make_recipe, add_row):
    """A row outside the recipe is not touched."""
    foreign = make_recipe(owner=other_user, name="Theirs")
    group = IngredientGroup.objects.create(recipe=foreign, group_name="", index_in_sequence=0)
    row = add_row(group, "salt")
    assert delete_row(recipe=recipe, row_id=row.pk) is None
    assert IngredientInRecipe.objects.filter(pk=row.pk).exists()


# --- delete_group ---


@pytest.mark.django_db
def test_delete_group_removes_it_and_its_rows(recipe, add_group, add_row):
    """A group goes with its rows, and the rest compact."""
    doomed, _kept = add_group("A"), add_group("B")
    add_row(doomed, "salt")
    assert delete_group(recipe=recipe, group_id=doomed.pk) is GroupDeletion.DELETED
    assert _layout(recipe) == [("B", [])]
    assert _indexes(recipe) == [0]


@pytest.mark.django_db
def test_delete_group_keeps_the_last_one(recipe, add_group):
    """A recipe's only group is refused."""
    group = add_group("A")
    assert delete_group(recipe=recipe, group_id=group.pk) is GroupDeletion.KEPT_LAST
    assert IngredientGroup.objects.filter(pk=group.pk).exists()


@pytest.mark.django_db
def test_delete_group_already_gone(recipe, add_group):
    """A group that no longer exists reports so."""
    group = add_group("A")
    add_group("B")
    missing = group.pk
    group.delete()
    assert delete_group(recipe=recipe, group_id=missing) is GroupDeletion.MISSING


# --- move_row ---


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("direction", "expected"), [("up", ["pepper", "salt"]), ("down", ["salt", "pepper"])]
)
def test_move_row(recipe, add_group, add_row, direction, expected):
    """A row swaps with its neighbour; at the edge nothing changes."""
    group = add_group("A")
    add_row(group, "salt")
    pepper = add_row(group, "pepper")
    assert move_row(recipe=recipe, row_id=pepper.pk, direction=direction) == group
    assert _layout(recipe) == [("A", expected)]


@pytest.mark.django_db
def test_move_row_gone_is_none(recipe, add_group, add_row):
    """A row that no longer exists moves nowhere."""
    row = add_row(add_group("A"), "salt")
    missing = row.pk
    row.delete()
    assert move_row(recipe=recipe, row_id=missing, direction="up") is None


# --- reassign_rows ---


@pytest.mark.django_db
def test_reassign_into_an_existing_group_keeps_page_order(recipe, add_group, add_row):
    """Moved rows merge with the target's rows in the order the page showed them."""
    first, second = add_group("A"), add_group("B")
    salt, pepper = add_row(first, "salt"), add_row(first, "pepper")
    add_row(second, "oil")
    reassign_rows(recipe=recipe, row_ids=[pepper.pk, salt.pk], target_group_id=second.pk)
    assert _layout(recipe) == [("B", ["salt", "pepper", "oil"])]


@pytest.mark.django_db
def test_reassign_compacts_the_source_group(recipe, add_group, add_row):
    """Rows left behind close the gaps."""
    first, second = add_group("A"), add_group("B")
    salt, _pepper, _oil = add_row(first, "salt"), add_row(first, "pepper"), add_row(first, "oil")
    reassign_rows(recipe=recipe, row_ids=[salt.pk], target_group_id=second.pk)
    assert list(
        IngredientInRecipe.objects.filter(ingredient_group=first)
        .order_by("index_in_sequence")
        .values_list("index_in_sequence", flat=True)
    ) == [0, 1]


@pytest.mark.django_db
def test_reassign_into_a_new_group_appends_it(recipe, add_group, add_row):
    """With no target id, a new group named as given goes at the end."""
    group = add_group("A")
    salt, _pepper = add_row(group, "salt"), add_row(group, "pepper")
    reassign_rows(recipe=recipe, row_ids=[salt.pk], target_group_id=None, new_group_name=" Dip ")
    assert _layout(recipe) == [("A", ["pepper"]), ("Dip", ["salt"])]


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["", "   ", "x" * 65])
def test_reassign_into_a_new_group_needs_a_valid_name(recipe, add_group, add_row, name):
    """A blank or over-long name is refused and nothing moves."""
    group = add_group("A")
    salt = add_row(group, "salt")
    with pytest.raises(ReassignError, match="Group name is required"):
        reassign_rows(recipe=recipe, row_ids=[salt.pk], target_group_id=None, new_group_name=name)
    assert _layout(recipe) == [("A", ["salt"])]


@pytest.mark.django_db
def test_reassign_to_a_foreign_group_is_refused(
    recipe, add_group, add_row, other_user, make_recipe
):
    """A target outside the recipe is an invalid group."""
    salt = add_row(add_group("A"), "salt")
    foreign = IngredientGroup.objects.create(
        recipe=make_recipe(owner=other_user, name="Theirs"), group_name="", index_in_sequence=0
    )
    with pytest.raises(ReassignError, match="Invalid group"):
        reassign_rows(recipe=recipe, row_ids=[salt.pk], target_group_id=foreign.pk)


@pytest.mark.django_db
def test_reassign_into_the_same_group_is_a_no_op(recipe, add_group, add_row):
    """Rows already in the target stay where they are."""
    group = add_group("A")
    salt = add_row(group, "salt")
    add_row(group, "pepper")
    reassign_rows(recipe=recipe, row_ids=[salt.pk], target_group_id=group.pk)
    assert _layout(recipe) == [("A", ["salt", "pepper"])]


@pytest.mark.django_db
def test_reassign_with_no_rows_of_the_recipe_creates_no_group(
    recipe, add_group, add_row, other_user, make_recipe
):
    """Foreign row ids are ignored, so no new group is made for nothing."""
    add_group("A")
    foreign = IngredientGroup.objects.create(
        recipe=make_recipe(owner=other_user, name="Theirs"), group_name="", index_in_sequence=0
    )
    row = add_row(foreign, "salt")
    reassign_rows(recipe=recipe, row_ids=[row.pk], target_group_id=None, new_group_name="Dip")
    assert _layout(recipe) == [("A", [])]
    row.refresh_from_db()
    assert row.ingredient_group_id == foreign.pk


@pytest.mark.django_db
def test_reassign_prunes_emptied_source_groups(recipe, add_group, add_row):
    """A source group left with nothing goes."""
    first, second = add_group("A"), add_group("B")
    salt = add_row(first, "salt")
    reassign_rows(recipe=recipe, row_ids=[salt.pk], target_group_id=second.pk)
    assert _layout(recipe) == [("B", ["salt"])]
    assert _indexes(recipe) == [0]
