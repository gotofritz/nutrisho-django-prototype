"""Tests for creating and saving rows, groups and steps through services (#77)."""

from decimal import Decimal

import pytest
from django.core.exceptions import ObjectDoesNotExist

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step
from recipes.services.ingredient_groups import (
    GroupNameError,
    create_group,
    create_row,
    rename_group,
    resolve_row_names,
    save_row,
)
from recipes.services.step_editing import create_step, save_step


@pytest.fixture
def recipe(user, make_recipe) -> Recipe:
    """A recipe owned by the test user."""
    return make_recipe(owner=user, name="Writes")


@pytest.fixture
def group(recipe) -> IngredientGroup:
    """The recipe's first group."""
    return IngredientGroup.objects.create(recipe=recipe, group_name="Main", index_in_sequence=0)


def _names(group: IngredientGroup) -> list[str]:
    return [
        r.ingredient.ingredient_name
        for r in IngredientInRecipe.objects.filter(ingredient_group=group).order_by(
            "index_in_sequence"
        )
    ]


def _groups(recipe: Recipe) -> list[str]:
    return [g.group_name for g in IngredientGroup.objects.filter(recipe=recipe)]


# --- resolve_row_names ---


@pytest.mark.django_db
def test_resolve_row_names_creates_new_ingredients_private_to_the_owner(user):
    """Unknown names become the owner's private ingredients."""
    row = IngredientInRecipe()
    resolve_row_names(row, owner=user, ingredient_name=" fresh-cheese ", substitute_name="other")
    assert row.ingredient.ingredient_name == "fresh-cheese"  # ty: ignore[unresolved-attribute]
    assert row.ingredient.owner == user  # ty: ignore[unresolved-attribute]
    assert row.substitute.ingredient_name == "other"  # ty: ignore[unresolved-attribute]


@pytest.mark.django_db
def test_resolve_row_names_reuses_and_clears(user, make_ingredient):
    """A known name is reused, and a blank substitute clears it."""
    basil = make_ingredient("basil")
    row = IngredientInRecipe(substitute=make_ingredient("mint"))
    resolve_row_names(row, owner=user, ingredient_name="basil", substitute_name="")
    assert row.ingredient == basil
    assert row.substitute is None


# --- create_row / save_row ---


@pytest.mark.django_db
def test_create_row_inserts_at_the_position(recipe, group, add_ingredient, make_ingredient):
    """The new row lands where the draft was, resolving its names."""
    add_ingredient(recipe=recipe, ingredient=make_ingredient("salt"))
    add_ingredient(recipe=recipe, ingredient=make_ingredient("oil"))
    row = create_row(
        recipe=recipe,
        group_id=group.pk,
        row=IngredientInRecipe(quantity=Decimal(2)),
        ingredient_name="garlic",
        position="1",
    )
    assert row.pk is not None
    assert _names(group) == ["salt", "garlic", "oil"]


@pytest.mark.django_db
def test_create_row_without_position_appends(recipe, group, add_ingredient, make_ingredient):
    """No position puts the row last."""
    add_ingredient(recipe=recipe, ingredient=make_ingredient("salt"))
    create_row(recipe=recipe, group_id=group.pk, row=IngredientInRecipe(), ingredient_name="oil")
    assert _names(group) == ["salt", "oil"]


@pytest.mark.django_db
def test_create_row_in_a_foreign_group_creates_nothing(recipe, other_user, make_recipe):
    """A group outside the recipe is missing, and no ingredient is made for it."""
    foreign = IngredientGroup.objects.create(
        recipe=make_recipe(owner=other_user, name="Theirs"), group_name="", index_in_sequence=0
    )
    with pytest.raises(ObjectDoesNotExist):
        create_row(
            recipe=recipe, group_id=foreign.pk, row=IngredientInRecipe(), ingredient_name="new-x"
        )
    assert not Ingredient.objects.filter(ingredient_name="new-x").exists()
    assert not IngredientInRecipe.objects.exists()


@pytest.mark.django_db
def test_save_row_writes_the_fields_and_names(recipe, add_ingredient, make_ingredient):
    """The row's own fields and both names are written."""
    row = add_ingredient(recipe=recipe, ingredient=make_ingredient("salt"))
    row.quantity, row.note = Decimal(3), "flaky"
    save_row(recipe=recipe, row=row, ingredient_name="sea salt", substitute_name="salt")
    row.refresh_from_db()
    assert (row.quantity, row.note) == (Decimal(3), "flaky")
    assert row.ingredient.ingredient_name == "sea salt"
    assert row.substitute.ingredient_name == "salt"


@pytest.mark.django_db
def test_save_row_does_not_move_it(recipe, group, add_ingredient, make_ingredient):
    """A concurrent reassign's group and position survive the save."""
    row = add_ingredient(recipe=recipe, ingredient=make_ingredient("salt"))
    other = IngredientGroup.objects.create(recipe=recipe, group_name="Dip", index_in_sequence=1)
    IngredientInRecipe.objects.filter(pk=row.pk).update(ingredient_group=other)
    save_row(recipe=recipe, row=row, ingredient_name="salt")
    row.refresh_from_db()
    assert row.ingredient_group_id == other.pk


@pytest.mark.django_db
def test_save_row_that_has_gone_raises(recipe, add_ingredient, make_ingredient):
    """A row deleted since the form opened is missing."""
    row = add_ingredient(recipe=recipe, ingredient=make_ingredient("salt"))
    IngredientInRecipe.objects.filter(pk=row.pk).delete()
    with pytest.raises(ObjectDoesNotExist):
        save_row(recipe=recipe, row=row, ingredient_name="salt")


# --- create_group / rename_group ---


@pytest.mark.django_db
def test_create_first_group_may_be_unnamed(recipe):
    """A recipe's only group needs no name."""
    created = create_group(recipe=recipe, name="  ")
    assert created.pk is not None
    assert _groups(recipe) == [""]


@pytest.mark.django_db
def test_create_second_group_needs_a_name(recipe, group):
    """Once there are two groups, each needs a name."""
    with pytest.raises(GroupNameError, match="Group name required"):
        create_group(recipe=recipe, name="")
    assert _groups(recipe) == ["Main"]


@pytest.mark.django_db
def test_create_group_inserts_at_the_position(recipe, group):
    """The new group lands where the draft was, its name trimmed."""
    create_group(recipe=recipe, name=" Dip ", position="0")
    assert _groups(recipe) == ["Dip", "Main"]


@pytest.mark.django_db
def test_rename_group(recipe, group):
    """A rename is trimmed and saved."""
    renamed = rename_group(recipe=recipe, group_id=group.pk, name=" Sauce ")
    assert renamed.group_name == "Sauce"
    assert _groups(recipe) == ["Sauce"]


@pytest.mark.django_db
def test_rename_one_of_several_groups_to_blank_is_refused(recipe, group):
    """Blanking a name is refused while the recipe has other groups."""
    IngredientGroup.objects.create(recipe=recipe, group_name="Dip", index_in_sequence=1)
    with pytest.raises(GroupNameError):
        rename_group(recipe=recipe, group_id=group.pk, name="")
    assert _groups(recipe) == ["Main", "Dip"]


@pytest.mark.django_db
def test_rename_only_group_to_blank(recipe, group):
    """The only group may lose its name."""
    rename_group(recipe=recipe, group_id=group.pk, name="")
    assert _groups(recipe) == [""]


@pytest.mark.django_db
def test_rename_group_that_has_gone_raises(recipe, group):
    """A group deleted since the form opened is missing."""
    missing = group.pk
    group.delete()
    with pytest.raises(ObjectDoesNotExist):
        rename_group(recipe=recipe, group_id=missing, name="Sauce")


# --- create_step / save_step ---


def _steps(recipe: Recipe) -> list[str]:
    return [s.step_text for s in Step.objects.filter(recipe=recipe).order_by("index_in_sequence")]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("position", "expected"),
    [
        ("0", ["New", "Boil.", "Serve."]),
        ("1", ["Boil.", "New", "Serve."]),
        (None, ["Boil.", "Serve.", "New"]),
    ],
)
def test_create_step_inserts_at_the_position(recipe, add_step, position, expected):
    """The new step lands where the draft was, or last."""
    add_step(recipe=recipe, text="Boil.")
    add_step(recipe=recipe, text="Serve.")
    step = create_step(recipe=recipe, step=Step(step_text="New"), position=position)
    assert step.pk is not None
    assert _steps(recipe) == expected


@pytest.mark.django_db
def test_create_step_in_a_deleted_recipe_raises(recipe):
    """A recipe deleted since the form opened gets no step."""
    Recipe.objects.filter(pk=recipe.pk).delete()
    with pytest.raises(ObjectDoesNotExist):
        create_step(recipe=recipe, step=Step(step_text="New"))
    assert not Step.objects.exists()


@pytest.mark.django_db
def test_save_step_writes_title_and_text(recipe, add_step):
    """Only the title and text are written."""
    step = add_step(recipe=recipe, text="Boil.")
    step.step_title, step.step_text = "Pasta", "Boil hard."
    save_step(recipe=recipe, step=step)
    step.refresh_from_db()
    assert (step.step_title, step.step_text) == ("Pasta", "Boil hard.")


@pytest.mark.django_db
def test_save_step_that_has_gone_raises(recipe, add_step):
    """A step deleted since the form opened is missing."""
    step = add_step(recipe=recipe, text="Boil.")
    Step.objects.filter(pk=step.pk).delete()
    with pytest.raises(ObjectDoesNotExist):
        save_step(recipe=recipe, step=step)
