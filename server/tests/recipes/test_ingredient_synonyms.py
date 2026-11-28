"""Common synonyms as aliases of the ingredient a user's lists hold (#203).

`soy sauce` clipped from an American page should land on `soya sauce`. The
alias mechanism is there (plan 008); what was missing is the synonyms
themselves, so a curated list adds them, a dry run first.
"""

from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command

from recipes.models import Ingredient, IngredientAlias, IngredientChange, IngredientInRecipe
from recipes.services.ingredient_journal import journaled, undo_change
from recipes.services.ingredient_synonyms import (
    SYNONYMS,
    apply_synonym_aliases,
    plan_synonym_aliases,
)
from recipes.services.name_resolution import find_ingredient

SOY = (("soya sauce", "soy sauce"),)


def _planned(plan) -> list[tuple[str, str, int, str]]:
    return [
        (entry.alias, entry.canonical.ingredient_name, entry.merges, entry.clash) for entry in plan
    ]


@pytest.mark.django_db
def test_plans_each_other_name_as_an_alias_of_the_one_the_lists_hold(make_ingredient):
    """The name the lists hold is the canonical; the others alias it."""
    make_ingredient("aubergine")
    plan = plan_synonym_aliases(synonyms=(("aubergine", "eggplant", "brinjal"),))
    assert _planned(plan) == [
        ("eggplant", "aubergine", 0, ""),
        ("brinjal", "aubergine", 0, ""),
    ]


@pytest.mark.django_db
def test_takes_the_first_name_held_when_it_is_not_the_british_one(make_ingredient):
    """Whichever spelling the lists hold stays canonical."""
    make_ingredient("soy sauce")
    assert _planned(plan_synonym_aliases(synonyms=SOY)) == [("soya sauce", "soy sauce", 0, "")]


@pytest.mark.django_db
def test_plans_nothing_for_names_the_lists_do_not_hold(make_ingredient):
    """No canonical, no alias: nothing to resolve to."""
    make_ingredient("lemon")
    assert plan_synonym_aliases(synonyms=SOY) == []


@pytest.mark.django_db
def test_a_private_row_is_never_the_canonical(user):
    """Aliases are global, so they point at global rows only."""
    Ingredient.objects.create(ingredient_name="soya sauce", owner=user)
    assert plan_synonym_aliases(synonyms=SOY) == []


@pytest.mark.django_db
def test_counts_the_rows_of_that_name_it_will_merge(user, make_ingredient):
    """A private `soy sauce` from an earlier clip is folded into the canonical."""
    make_ingredient("soya sauce")
    Ingredient.objects.create(ingredient_name="Soy sauce", owner=user)
    assert _planned(plan_synonym_aliases(synonyms=SOY)) == [("soy sauce", "soya sauce", 1, "")]


@pytest.mark.django_db
def test_skips_a_name_that_already_resolves(make_ingredient):
    """An alias already there, or the canonical's own plural, needs nothing."""
    soya = make_ingredient("soya sauce")
    IngredientAlias.objects.create(alias_name="Soy Sauce", canonical=soya)
    make_ingredient("chickpea")
    plan = plan_synonym_aliases(synonyms=(*SOY, ("chickpea", "chickpeas", "garbanzo")))
    assert _planned(plan) == [("garbanzo", "chickpea", 0, "")]


@pytest.mark.django_db
def test_leaves_a_name_aliased_to_another_ingredient_alone_and_says_so(make_ingredient):
    """Staff chose otherwise for that name; the list does not overrule them."""
    make_ingredient("soya sauce")
    tamari = make_ingredient("tamari")
    IngredientAlias.objects.create(alias_name="soy sauce", canonical=tamari)
    assert _planned(plan_synonym_aliases(synonyms=SOY)) == [
        ("soy sauce", "soya sauce", 0, "already an alias of “tamari”")
    ]


@pytest.mark.django_db
def test_applying_adds_the_aliases_and_repoints_the_merged_rows(
    user, make_ingredient, make_recipe, add_ingredient
):
    """After it, `soy sauce` resolves to `soya sauce`, and a recipe that used it does too."""
    soya = make_ingredient("soya sauce")
    private = Ingredient.objects.create(ingredient_name="soy sauce", owner=user)
    row = add_ingredient(recipe=make_recipe(owner=user, name="Noodles"), ingredient=private)

    with journaled(user=user) as journal:
        added = apply_synonym_aliases(plan_synonym_aliases(synonyms=SOY), journal=journal)

    assert added == 1
    assert find_ingredient("soy sauce", owner=user) == soya
    assert find_ingredient("soy sauces", owner=user) == soya
    assert IngredientInRecipe.objects.get(pk=row.pk).ingredient == soya
    assert not Ingredient.objects.filter(pk=private.pk).exists()


@pytest.mark.django_db
def test_applying_is_one_change_that_undo_takes_back(user, make_ingredient):
    """The clean-up tool's Undo reverses the whole run."""
    make_ingredient("soya sauce")
    make_ingredient("aubergine")
    with journaled(user=user) as journal:
        apply_synonym_aliases(
            plan_synonym_aliases(synonyms=(*SOY, ("aubergine", "eggplant"))), journal=journal
        )

    change = IngredientChange.objects.get()
    assert change.summary == "Added 2 synonyms as aliases"
    undo_change(change_id=change.pk)
    assert not IngredientAlias.objects.exists()


@pytest.mark.django_db
def test_applying_skips_the_clashes(user, make_ingredient):
    """A clash in the plan is reported, never written."""
    make_ingredient("soya sauce")
    IngredientAlias.objects.create(alias_name="soy sauce", canonical=make_ingredient("tamari"))
    with journaled(user=user) as journal:
        added = apply_synonym_aliases(plan_synonym_aliases(synonyms=SOY), journal=journal)
    assert added == 0
    assert IngredientAlias.objects.get().canonical.ingredient_name == "tamari"
    assert not IngredientChange.objects.exists()


def test_the_list_names_each_synonym_once():
    """A name in two groups would alias two ingredients."""
    names = [name.lower() for group in SYNONYMS for name in group]
    assert len(names) == len(set(names))
    assert all(len(group) >= 2 for group in SYNONYMS)


def test_the_list_holds_the_synonyms_the_issue_names():
    """`soy sauce`/`soya sauce` and `aubergine`/`eggplant` (#203)."""
    groups = {group[0]: group[1:] for group in SYNONYMS}
    assert "soy sauce" in groups["soya sauce"]
    assert "eggplant" in groups["aubergine"]


@pytest.fixture
def owner(db):
    """The site owner, whom the command journals the change as."""
    return User.objects.create_superuser(username="owner", password="x")


@pytest.mark.django_db
def test_the_command_lists_the_plan_and_writes_nothing_by_default(owner, make_ingredient):
    """A dry run, as `normalise_units` is."""
    make_ingredient("soya sauce")
    out = StringIO()
    call_command("add_ingredient_synonyms", stdout=out)
    assert "soy sauce → soya sauce" in out.getvalue()
    assert "Dry run" in out.getvalue()
    assert not IngredientAlias.objects.exists()


@pytest.mark.django_db
def test_the_command_applies_the_plan_as_the_owner(owner, user, make_ingredient):
    """`--apply` writes it, journalled as the first superuser, so Undo can take it back."""
    make_ingredient("soya sauce")
    Ingredient.objects.create(ingredient_name="soy sauce", owner=user)
    out = StringIO()
    call_command("add_ingredient_synonyms", "--apply", stdout=out)
    assert "soy sauce → soya sauce, merging 1 ingredient row" in out.getvalue()
    assert "Added 1 alias." in out.getvalue()
    assert IngredientAlias.objects.get().alias_name == "soy sauce"
    assert IngredientChange.objects.get().user == owner


@pytest.mark.django_db
def test_the_command_says_when_there_is_nothing_to_add(owner):
    """With none of the names held, it says so."""
    out = StringIO()
    call_command("add_ingredient_synonyms", stdout=out)
    assert "No synonyms to add." in out.getvalue()


@pytest.mark.django_db
def test_the_command_needs_an_owner_to_apply(make_ingredient):
    """Undo needs someone to name, so there must be a superuser."""
    make_ingredient("soya sauce")
    with pytest.raises(CommandError, match="make bootstrap"):
        call_command("add_ingredient_synonyms", "--apply", stdout=StringIO())
