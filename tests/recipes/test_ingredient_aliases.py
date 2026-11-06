"""Ingredient aliases: input-only names for a canonical ingredient (plan 008, #66).

`eggplant → aubergine` lets scraped or typed variants land on the British
canonical row. Aliases are global and staff-defined (plan 011), never rows of
their own and never referenced by a recipe.
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from recipes.forms.ingredient_admin_forms import IngredientForm
from recipes.models import Ingredient, IngredientAlias, IngredientInRecipe
from recipes.services.ingredient_admin import (
    AliasError,
    add_alias,
    delete_ingredients,
    merge_ingredients,
    merge_plural_ingredients,
    remove_alias,
)
from recipes.services.name_resolution import find_ingredient, resolve_ingredient


@pytest.fixture
def aubergine(make_ingredient):
    """A global canonical ingredient."""
    return make_ingredient("aubergine")


@pytest.mark.django_db
def test_an_alias_points_at_its_canonical(aubergine):
    """An alias is a name plus the ingredient it stands for."""
    alias = IngredientAlias.objects.create(alias_name="eggplant", canonical=aubergine)
    assert list(aubergine.aliases.all()) == [alias]
    assert str(alias) == "eggplant → aubergine"


@pytest.mark.django_db
def test_alias_names_are_unique_ignoring_case(aubergine, make_ingredient):
    """`Eggplant` cannot alias one ingredient while `eggplant` aliases another."""
    IngredientAlias.objects.create(alias_name="eggplant", canonical=aubergine)
    with pytest.raises(IntegrityError):
        IngredientAlias.objects.create(alias_name="Eggplant", canonical=make_ingredient("brinjal"))


@pytest.mark.django_db
def test_an_alias_cannot_share_a_name_with_an_ingredient(aubergine, make_ingredient):
    """A name is either an ingredient or an alias, never both."""
    make_ingredient("eggplant")
    with pytest.raises(ValidationError, match="already an ingredient"):
        IngredientAlias(alias_name="EGGPLANT", canonical=aubergine).full_clean()


@pytest.mark.django_db
def test_an_alias_cannot_share_a_name_with_a_private_ingredient(aubergine, user):
    """Private rows count too: the alias would hide them from their owner."""
    Ingredient.objects.create(ingredient_name="eggplant", owner=user)
    with pytest.raises(ValidationError, match="already an ingredient"):
        IngredientAlias(alias_name="eggplant", canonical=aubergine).full_clean()


@pytest.mark.django_db
def test_an_alias_must_point_at_a_global_ingredient(user):
    """Aliases are global, so their canonical has to be visible to everyone."""
    private = Ingredient.objects.create(ingredient_name="aubergine", owner=user)
    with pytest.raises(ValidationError, match="global"):
        IngredientAlias(alias_name="eggplant", canonical=private).full_clean()


@pytest.mark.django_db
def test_a_duplicate_alias_fails_validation(aubergine):
    """The case-insensitive uniqueness shows up as a form error, not a 500."""
    IngredientAlias.objects.create(alias_name="eggplant", canonical=aubergine)
    with pytest.raises(ValidationError, match="already an alias"):
        IngredientAlias(alias_name="Eggplant", canonical=aubergine).full_clean()


@pytest.mark.django_db
def test_deleting_the_canonical_deletes_its_aliases(aubergine):
    """Aliases cascade with their canonical."""
    IngredientAlias.objects.create(alias_name="eggplant", canonical=aubergine)
    aubergine.delete()
    assert not IngredientAlias.objects.exists()


@pytest.mark.django_db
def test_resolve_maps_an_alias_to_its_canonical(aubergine, user):
    """Typing `eggplant` stores `aubergine`, and creates no row (#66)."""
    IngredientAlias.objects.create(alias_name="eggplant", canonical=aubergine)
    assert resolve_ingredient(" Eggplant ", owner=user) == aubergine
    assert Ingredient.objects.count() == 1


@pytest.mark.django_db
def test_resolve_maps_an_aliases_plural_to_its_canonical(aubergine, user):
    """`2 eggplants` is `aubergine` too: the alias's rule plural matches."""
    IngredientAlias.objects.create(alias_name="eggplant", canonical=aubergine)
    assert resolve_ingredient("eggplants", owner=user) == aubergine


@pytest.mark.django_db
def test_find_ingredient_follows_aliases(aubergine, user):
    """The editor's no-create lookup follows aliases as well."""
    IngredientAlias.objects.create(alias_name="eggplant", canonical=aubergine)
    assert find_ingredient("eggplant", owner=user) == aubergine


@pytest.mark.django_db
def test_resolve_still_creates_an_unknown_name(aubergine, user):
    """An alias never swallows a name it does not spell."""
    IngredientAlias.objects.create(alias_name="eggplant", canonical=aubergine)
    created = resolve_ingredient("egg", owner=user)
    assert created.ingredient_name == "egg"
    assert created.owner == user


@pytest.mark.django_db
def test_an_ingredient_cannot_be_renamed_onto_an_alias(aubergine, make_ingredient):
    """The clean-up tool's Edit keeps a name from being both (plan 008)."""
    IngredientAlias.objects.create(alias_name="eggplant", canonical=aubergine)
    brinjal = make_ingredient("brinjal")
    form = IngredientForm(data={"ingredient_name": "Eggplant"}, instance=brinjal)
    assert not form.is_valid()
    assert "alias of “aubergine”" in form.errors["ingredient_name"][0]


def _aliases() -> dict[str, str]:
    return dict(IngredientAlias.objects.values_list("alias_name", "canonical__ingredient_name"))


@pytest.mark.django_db
def test_merge_records_each_victims_name_as_an_alias(aubergine, make_ingredient, user):
    """Merging `eggplant` into `aubergine` keeps `eggplant` typeable (phase 4)."""
    eggplant = make_ingredient("eggplant")
    merge_ingredients(survivor_id=aubergine.pk, victim_ids=[aubergine.pk, eggplant.pk])
    assert _aliases() == {"eggplant": "aubergine"}
    assert resolve_ingredient("eggplant", owner=user) == aubergine
    assert Ingredient.objects.count() == 1


@pytest.mark.django_db
def test_merge_repoints_the_victims_aliases_to_the_survivor(aubergine, make_ingredient):
    """No alias is orphaned: the victim's own aliases follow its recipes."""
    eggplant = make_ingredient("eggplant")
    IngredientAlias.objects.create(alias_name="brinjal", canonical=eggplant)
    merge_ingredients(survivor_id=aubergine.pk, victim_ids=[eggplant.pk])
    assert _aliases() == {"brinjal": "aubergine", "eggplant": "aubergine"}


@pytest.mark.django_db
def test_merge_skips_a_name_that_already_resolves_to_the_survivor(make_ingredient):
    """A case variant or a plural of the survivor needs no alias."""
    onion = make_ingredient("onion")
    onions = make_ingredient("onions")
    merge_ingredients(survivor_id=onion.pk, victim_ids=[onions.pk])
    assert not IngredientAlias.objects.exists()


@pytest.mark.django_db
def test_merge_into_a_private_survivor_records_no_alias(user):
    """Aliases are global, so a private survivor gets none (plan 011)."""
    survivor = Ingredient.objects.create(ingredient_name="aubergine", owner=user)
    victim = Ingredient.objects.create(ingredient_name="eggplant", owner=user)
    merge_ingredients(survivor_id=survivor.pk, victim_ids=[victim.pk])
    assert not IngredientAlias.objects.exists()


@pytest.mark.django_db
def test_merge_folds_other_users_rows_of_the_victims_name(
    aubergine, make_ingredient, make_recipe, add_ingredient, other_user
):
    """Their private `eggplant` would clash with the new alias, so it joins too."""
    theirs = Ingredient.objects.create(ingredient_name="Eggplant", owner=other_user)
    recipe = make_recipe(owner=other_user, name="Baba ganoush")
    iir = add_ingredient(recipe=recipe, ingredient=theirs)
    merge_ingredients(survivor_id=aubergine.pk, victim_ids=[make_ingredient("eggplant").pk])
    iir.refresh_from_db()
    assert iir.ingredient == aubergine
    assert not Ingredient.objects.filter(pk=theirs.pk).exists()


@pytest.mark.django_db
def test_merge_plural_keeps_the_plurals_aliases(make_ingredient):
    """Folding a plural row carries its aliases to the singular."""
    tomato = make_ingredient("tomato")
    tomatoes = make_ingredient("tomatoes")
    IngredientAlias.objects.create(alias_name="pomodori", canonical=tomatoes)
    merge_plural_ingredients(singular_id=tomato.pk, plural_id=tomatoes.pk)
    assert _aliases() == {"pomodori": "tomato"}


@pytest.mark.django_db
def test_delete_with_a_replacement_moves_aliases_to_it(aubergine, make_ingredient):
    """A replacement inherits the deleted row's aliases along with its recipes."""
    eggplant = make_ingredient("eggplant")
    IngredientAlias.objects.create(alias_name="brinjal", canonical=eggplant)
    delete_ingredients(ingredient_ids=[eggplant.pk], replacement_id=aubergine.pk)
    assert _aliases() == {"brinjal": "aubergine"}


@pytest.mark.django_db
def test_delete_without_a_replacement_drops_its_aliases(make_ingredient):
    """With nothing to inherit them, the aliases go with the row."""
    eggplant = make_ingredient("eggplant")
    IngredientAlias.objects.create(alias_name="brinjal", canonical=eggplant)
    delete_ingredients(ingredient_ids=[eggplant.pk])
    assert not IngredientAlias.objects.exists()


@pytest.mark.django_db
def test_add_alias_creates_a_mapping_that_resolves(aubergine, user):
    """The explicit path (phase 5): declare `eggplant` before it is ever typed."""
    assert add_alias(canonical_id=aubergine.pk, alias_name=" eggplant ") == 0
    assert _aliases() == {"eggplant": "aubergine"}
    assert resolve_ingredient("eggplant", owner=user) == aubergine


@pytest.mark.django_db
def test_add_alias_is_idempotent_for_the_same_canonical(aubergine):
    """Adding the same alias twice is not an error."""
    add_alias(canonical_id=aubergine.pk, alias_name="eggplant")
    add_alias(canonical_id=aubergine.pk, alias_name="Eggplant")
    assert IngredientAlias.objects.count() == 1


@pytest.mark.django_db
def test_add_alias_refuses_a_name_aliasing_another_ingredient(aubergine, make_ingredient):
    """One alias, one canonical."""
    add_alias(canonical_id=aubergine.pk, alias_name="eggplant")
    with pytest.raises(AliasError, match="already an alias of “aubergine”"):
        add_alias(canonical_id=make_ingredient("brinjal").pk, alias_name="EGGPLANT")


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["", "  ", "Aubergine", "aubergines"])
def test_add_alias_refuses_a_blank_name_or_one_that_already_resolves(aubergine, name):
    """Blank, the canonical's own name and its plural are not aliases."""
    with pytest.raises(AliasError):
        add_alias(canonical_id=aubergine.pk, alias_name=name)
    assert not IngredientAlias.objects.exists()


@pytest.mark.django_db
def test_add_alias_refuses_a_private_canonical(user):
    """Promote first: aliases only point at global rows."""
    private = Ingredient.objects.create(ingredient_name="aubergine", owner=user)
    with pytest.raises(AliasError, match="promote it first"):
        add_alias(canonical_id=private.pk, alias_name="eggplant")


@pytest.mark.django_db
def test_add_alias_onto_an_existing_row_merges_it(
    aubergine, make_ingredient, make_recipe, add_ingredient, user, other_user
):
    """Convergence (phase 6): every `eggplant` row, anyone's, folds into the canonical."""
    eggplant = make_ingredient("eggplant")
    theirs = Ingredient.objects.create(ingredient_name="EggPlant", owner=other_user)
    mine = add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=eggplant)
    their_iir = add_ingredient(
        recipe=make_recipe(owner=other_user, name="Caponata"), ingredient=make_ingredient("basil")
    )
    their_iir.substitute = theirs
    their_iir.save()
    assert add_alias(canonical_id=aubergine.pk, alias_name="eggplant") == 2
    assert set(
        IngredientInRecipe.objects.values_list("ingredient__ingredient_name", flat=True)
    ) == {
        "aubergine",
        "basil",
    }
    their_iir.refresh_from_db()
    assert their_iir.substitute == aubergine
    mine.refresh_from_db()
    assert mine.ingredient == aubergine
    assert _aliases() == {"eggplant": "aubergine"}


@pytest.mark.django_db
def test_remove_alias_deletes_the_mapping(aubergine, user):
    """Removing an alias makes the name unknown again."""
    alias = IngredientAlias.objects.create(alias_name="eggplant", canonical=aubergine)
    remove_alias(alias_id=alias.pk)
    assert not IngredientAlias.objects.exists()
    assert resolve_ingredient("eggplant", owner=user) != aubergine
