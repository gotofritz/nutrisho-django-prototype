"""Tests for the ingredient-admin service layer (Plan 007)."""

import pytest
from django.core.exceptions import ObjectDoesNotExist

from recipes.models import Ingredient, IngredientInRecipe
from recipes.services.ingredient_admin import (
    IngredientInUseError,
    delete_ingredients,
    find_ingredient_duplicates,
    find_plural_duplicates,
    merge_ingredients,
    merge_plural_ingredients,
    recipes_for_ingredients,
    recipes_referencing_ingredients,
    search_ingredients,
    selected_ingredients,
    suggest_singular,
)


@pytest.mark.django_db
def test_search_ingredients_empty_query_returns_all_case_insensitively_sorted(make_ingredient):
    make_ingredient("onion")
    make_ingredient("Carrot")
    make_ingredient("aubergine")
    names = [i.ingredient_name for i in search_ingredients("")]
    assert names == ["aubergine", "Carrot", "onion"]


@pytest.mark.django_db
def test_search_ingredients_matches_case_insensitive_substring(make_ingredient):
    make_ingredient("onion")
    make_ingredient("spring onions")
    make_ingredient("aubergine")
    names = [i.ingredient_name for i in search_ingredients("ONI")]
    assert names == ["onion", "spring onions"]


@pytest.mark.django_db
def test_search_ingredients_orders_case_variants_adjacently_and_stably(
    without_ci_name_constraint, make_ingredient
):
    """Legacy databases predate ingredient_name_ci_unique and still hold variants.

    Those are exactly the rows the clean-up tool exists to merge, so they have to
    land next to each other, in a stable order.
    """
    make_ingredient("apple")
    make_ingredient("onion")
    make_ingredient("Onion")
    names = [i.ingredient_name for i in search_ingredients("")]
    assert names == ["apple", "Onion", "onion"]


@pytest.mark.django_db
def test_search_ingredients_no_match_returns_empty(make_ingredient):
    make_ingredient("onion")
    assert list(search_ingredients("zzz")) == []


@pytest.mark.django_db
def test_recipes_for_ingredients_returns_recipes_using_the_ingredient(
    user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    make_recipe(owner=user, name="Pancakes")
    add_ingredient(recipe=moussaka, ingredient=onion)
    matches = recipes_for_ingredients(ingredient_ids=[onion.pk], owner=user)
    assert [r.recipe_name for r in matches] == ["Moussaka"]


@pytest.mark.django_db
def test_recipes_for_ingredients_unions_across_selected_ingredients(
    user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    aubergine = make_ingredient("aubergine")
    moussaka = make_recipe(owner=user, name="Moussaka")
    ratatouille = make_recipe(owner=user, name="Ratatouille")
    add_ingredient(recipe=moussaka, ingredient=onion)
    add_ingredient(recipe=ratatouille, ingredient=aubergine)
    matches = recipes_for_ingredients(ingredient_ids=[onion.pk, aubergine.pk], owner=user)
    assert [r.recipe_name for r in matches] == ["Moussaka", "Ratatouille"]


@pytest.mark.django_db
def test_recipes_for_ingredients_empty_selection_returns_nothing(
    user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    assert list(recipes_for_ingredients(ingredient_ids=[], owner=user)) == []


@pytest.mark.django_db
def test_recipes_for_ingredients_lists_a_recipe_once_per_repeated_use(
    user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    add_ingredient(recipe=moussaka, ingredient=onion)
    matches = recipes_for_ingredients(ingredient_ids=[onion.pk], owner=user)
    assert [r.recipe_name for r in matches] == ["Moussaka"]


@pytest.mark.django_db
def test_recipes_for_ingredients_is_owner_scoped(
    user, other_user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    theirs = make_recipe(owner=other_user, name="Their Soup")
    add_ingredient(recipe=theirs, ingredient=onion)
    assert list(recipes_for_ingredients(ingredient_ids=[onion.pk], owner=user)) == []


@pytest.mark.django_db
def test_recipes_for_ingredients_includes_substitute_references(
    user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    shallot = make_ingredient("shallot")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion, substitute=shallot)
    matches = recipes_for_ingredients(ingredient_ids=[shallot.pk], owner=user)
    assert [r.recipe_name for r in matches] == ["Moussaka"]


@pytest.mark.django_db
def test_selected_ingredients_orders_like_the_ingredient_column(make_ingredient):
    onion = make_ingredient("onion")
    aubergine = make_ingredient("Aubergine")
    carrot = make_ingredient("carrot")
    picked = selected_ingredients([onion.pk, carrot.pk, aubergine.pk])
    assert [i.ingredient_name for i in picked] == ["Aubergine", "carrot", "onion"]


@pytest.mark.django_db
def test_selected_ingredients_ignores_unknown_ids(make_ingredient):
    onion = make_ingredient("onion")
    picked = selected_ingredients([onion.pk, 9999])
    assert [i.ingredient_name for i in picked] == ["onion"]


@pytest.mark.django_db
def test_selected_ingredients_with_no_ids_is_empty(make_ingredient):
    make_ingredient("onion")
    assert list(selected_ingredients([])) == []


@pytest.mark.django_db
def test_recipes_referencing_ingredients_is_not_owner_scoped(
    other_user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    theirs = make_recipe(owner=other_user, name="Their Soup")
    add_ingredient(recipe=theirs, ingredient=onion)
    matches = recipes_referencing_ingredients([onion.pk])
    assert [r.recipe_name for r in matches] == ["Their Soup"]


@pytest.mark.django_db
def test_delete_ingredients_removes_unused_rows(make_ingredient):
    onion = make_ingredient("onion")
    keep = make_ingredient("carrot")
    assert delete_ingredients(ingredient_ids=[onion.pk]) == 1
    assert list(Ingredient.objects.values_list("pk", flat=True)) == [keep.pk]


@pytest.mark.django_db
def test_delete_ingredients_repoints_the_ingredient_fk_to_the_replacement(
    user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    shallot = make_ingredient("shallot")
    moussaka = make_recipe(owner=user, name="Moussaka")
    iir = add_ingredient(recipe=moussaka, ingredient=onion)
    delete_ingredients(ingredient_ids=[onion.pk], replacement_id=shallot.pk)
    iir.refresh_from_db()
    assert iir.ingredient_id == shallot.pk
    assert not Ingredient.objects.filter(pk=onion.pk).exists()


@pytest.mark.django_db
def test_delete_ingredients_repoints_the_substitute_fk_too(
    user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    shallot = make_ingredient("shallot")
    leek = make_ingredient("leek")
    moussaka = make_recipe(owner=user, name="Moussaka")
    iir = add_ingredient(recipe=moussaka, ingredient=leek, substitute=onion)
    delete_ingredients(ingredient_ids=[onion.pk], replacement_id=shallot.pk)
    iir.refresh_from_db()
    assert iir.substitute_id == shallot.pk
    assert not Ingredient.objects.filter(pk=onion.pk).exists()


@pytest.mark.django_db
def test_delete_ingredients_leaves_index_in_sequence_untouched(
    user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    shallot = make_ingredient("shallot")
    carrot = make_ingredient("carrot")
    moussaka = make_recipe(owner=user, name="Moussaka")
    first = add_ingredient(recipe=moussaka, ingredient=carrot)
    second = add_ingredient(recipe=moussaka, ingredient=onion)
    delete_ingredients(ingredient_ids=[onion.pk], replacement_id=shallot.pk)
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.index_in_sequence, second.index_in_sequence) == (0, 1)


@pytest.mark.django_db
def test_delete_ingredients_refuses_a_used_ingredient_without_a_replacement(
    user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    with pytest.raises(IngredientInUseError):
        delete_ingredients(ingredient_ids=[onion.pk])
    assert Ingredient.objects.filter(pk=onion.pk).exists()


@pytest.mark.django_db
def test_delete_ingredients_refuses_an_unknown_replacement(
    user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    with pytest.raises(IngredientInUseError):
        delete_ingredients(ingredient_ids=[onion.pk], replacement_id=9999)
    assert Ingredient.objects.filter(pk=onion.pk).exists()


@pytest.mark.django_db
def test_delete_ingredients_never_deletes_the_replacement(
    user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    shallot = make_ingredient("shallot")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=onion)
    delete_ingredients(ingredient_ids=[onion.pk, shallot.pk], replacement_id=shallot.pk)
    assert Ingredient.objects.filter(pk=shallot.pk).exists()
    assert not Ingredient.objects.filter(pk=onion.pk).exists()


@pytest.mark.django_db
def test_delete_ingredients_with_no_ids_is_a_no_op(make_ingredient):
    make_ingredient("onion")
    assert delete_ingredients(ingredient_ids=[]) == 0
    assert Ingredient.objects.count() == 1


@pytest.mark.django_db
def test_merge_ingredients_repoints_recipes_onto_the_survivor(
    user, make_ingredient, make_recipe, add_ingredient
):
    aubergine = make_ingredient("aubergine")
    eggplant = make_ingredient("eggplant")
    iir = add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=eggplant)
    assert merge_ingredients(survivor_id=aubergine.pk, victim_ids=[eggplant.pk]) == 1
    iir.refresh_from_db()
    assert iir.ingredient_id == aubergine.pk
    assert not Ingredient.objects.filter(pk=eggplant.pk).exists()


@pytest.mark.django_db
def test_merge_ingredients_repoints_substitute_references_too(
    user, make_ingredient, make_recipe, add_ingredient
):
    aubergine = make_ingredient("aubergine")
    eggplant = make_ingredient("eggplant")
    courgette = make_ingredient("courgette")
    iir = add_ingredient(
        recipe=make_recipe(owner=user, name="Moussaka"),
        ingredient=courgette,
        substitute=eggplant,
    )
    merge_ingredients(survivor_id=aubergine.pk, victim_ids=[eggplant.pk])
    iir.refresh_from_db()
    assert iir.substitute_id == aubergine.pk


@pytest.mark.django_db
def test_merge_ingredients_leaves_the_survivor_row_untouched(make_ingredient):
    aubergine = Ingredient.objects.create(
        ingredient_name="aubergine", family="VEG", dietary_constraint="VGN"
    )
    eggplant = make_ingredient("eggplant")
    merge_ingredients(survivor_id=aubergine.pk, victim_ids=[eggplant.pk])
    aubergine.refresh_from_db()
    assert aubergine.ingredient_name == "aubergine"
    assert aubergine.family == "VEG"
    assert aubergine.dietary_constraint == "VGN"


@pytest.mark.django_db
def test_merge_ingredients_never_deletes_the_survivor(make_ingredient):
    aubergine = make_ingredient("aubergine")
    eggplant = make_ingredient("eggplant")
    merge_ingredients(survivor_id=aubergine.pk, victim_ids=[aubergine.pk, eggplant.pk])
    assert Ingredient.objects.filter(pk=aubergine.pk).exists()


@pytest.mark.django_db
def test_merge_ingredients_is_a_no_op_when_re_run(make_ingredient):
    aubergine = make_ingredient("aubergine")
    eggplant = make_ingredient("eggplant")
    merge_ingredients(survivor_id=aubergine.pk, victim_ids=[eggplant.pk])
    assert merge_ingredients(survivor_id=aubergine.pk, victim_ids=[eggplant.pk]) == 0


@pytest.mark.django_db
def test_merge_ingredients_rejects_an_unknown_survivor(make_ingredient):
    eggplant = make_ingredient("eggplant")
    with pytest.raises(ObjectDoesNotExist):
        merge_ingredients(survivor_id=9999, victim_ids=[eggplant.pk])
    assert Ingredient.objects.filter(pk=eggplant.pk).exists()


@pytest.mark.django_db
def test_merge_ingredients_leaves_index_in_sequence_untouched(
    user, make_ingredient, make_recipe, add_ingredient
):
    aubergine = make_ingredient("aubergine")
    eggplant = make_ingredient("eggplant")
    moussaka = make_recipe(owner=user, name="Moussaka")
    first = add_ingredient(recipe=moussaka, ingredient=aubergine)
    second = add_ingredient(recipe=moussaka, ingredient=eggplant)
    merge_ingredients(survivor_id=aubergine.pk, victim_ids=[eggplant.pk])
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.index_in_sequence, second.index_in_sequence) == (0, 1)


@pytest.mark.django_db
def test_merge_keeps_both_rows_when_a_recipe_used_survivor_and_victim(
    user, make_ingredient, make_recipe, add_ingredient
):
    """Documents Plan 007, 6.3: de-duplicating the group is out of scope."""
    aubergine = make_ingredient("aubergine")
    eggplant = make_ingredient("eggplant")
    moussaka = make_recipe(owner=user, name="Moussaka")
    add_ingredient(recipe=moussaka, ingredient=aubergine)
    add_ingredient(recipe=moussaka, ingredient=eggplant)
    merge_ingredients(survivor_id=aubergine.pk, victim_ids=[eggplant.pk])
    rows = IngredientInRecipe.objects.filter(ingredient_group__recipe=moussaka)
    assert rows.count() == 2
    assert {row.ingredient_id for row in rows} == {aubergine.pk}


@pytest.mark.django_db
def test_find_ingredient_duplicates_groups_case_variants(
    without_ci_name_constraint, make_ingredient
):
    onion = make_ingredient("onion")
    capital = make_ingredient("Onion")
    make_ingredient("carrot")
    assert [[i.pk for i in group] for group in find_ingredient_duplicates()] == [
        [capital.pk, onion.pk]
    ]


@pytest.mark.django_db
def test_find_ingredient_duplicates_groups_three_variants(
    without_ci_name_constraint, make_ingredient
):
    for name in ("onion", "Onion", "ONION"):
        make_ingredient(name)
    groups = find_ingredient_duplicates()
    assert len(groups) == 1
    assert [i.ingredient_name for i in groups[0]] == ["ONION", "Onion", "onion"]


@pytest.mark.django_db
def test_find_ingredient_duplicates_finds_every_clashing_group(
    without_ci_name_constraint, make_ingredient
):
    for name in ("onion", "Onion", "carrot", "Carrot", "leek"):
        make_ingredient(name)
    groups = find_ingredient_duplicates()
    assert [[i.ingredient_name for i in group] for group in groups] == [
        ["Carrot", "carrot"],
        ["Onion", "onion"],
    ]


@pytest.mark.django_db
def test_find_ingredient_duplicates_on_a_clean_database_is_empty(make_ingredient):
    make_ingredient("onion")
    make_ingredient("carrot")
    assert find_ingredient_duplicates() == []


@pytest.mark.django_db
def test_search_ingredients_unused_only_hides_ingredients_recipes_use(
    user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    make_ingredient("leftover")
    add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=onion)
    names = [i.ingredient_name for i in search_ingredients("", unused_only=True)]
    assert names == ["leftover"]


@pytest.mark.django_db
def test_search_ingredients_unused_only_counts_substitute_references_as_used(
    user, make_ingredient, make_recipe, add_ingredient
):
    """A substitute reference still PROTECTs the row, so it is not an orphan."""
    onion = make_ingredient("onion")
    shallot = make_ingredient("shallot")
    add_ingredient(
        recipe=make_recipe(owner=user, name="Moussaka"), ingredient=onion, substitute=shallot
    )
    assert list(search_ingredients("", unused_only=True)) == []


@pytest.mark.django_db
def test_search_ingredients_unused_only_ignores_who_owns_the_recipe(
    other_user, make_ingredient, make_recipe, add_ingredient
):
    """Ingredients are shared, so another owner's recipe still makes one used."""
    onion = make_ingredient("onion")
    add_ingredient(recipe=make_recipe(owner=other_user, name="Their Soup"), ingredient=onion)
    assert list(search_ingredients("", unused_only=True)) == []


@pytest.mark.django_db
def test_search_ingredients_unused_only_combines_with_the_query(
    user, make_ingredient, make_recipe, add_ingredient
):
    make_ingredient("spring onion")
    used = make_ingredient("onion")
    make_ingredient("carrot")
    add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=used)
    names = [i.ingredient_name for i in search_ingredients("oni", unused_only=True)]
    assert names == ["spring onion"]


@pytest.mark.django_db
def test_search_ingredients_without_the_flag_still_lists_used_ingredients(
    user, make_ingredient, make_recipe, add_ingredient
):
    onion = make_ingredient("onion")
    add_ingredient(recipe=make_recipe(owner=user, name="Moussaka"), ingredient=onion)
    assert [i.ingredient_name for i in search_ingredients("")] == ["onion"]


@pytest.mark.django_db
def test_find_plural_duplicates_pairs_a_singular_with_its_plural_row(make_ingredient):
    """An `onions` row next to `onion` is bad data — the display adds the s."""
    onion = make_ingredient("onion")
    onions = make_ingredient("onions")
    make_ingredient("carrot")
    assert find_plural_duplicates() == [[onion, onions]]


@pytest.mark.django_db
def test_find_plural_duplicates_uses_the_rule_not_a_bare_s(make_ingredient):
    tomato = make_ingredient("tomato")
    tomatoes = make_ingredient("tomatoes")
    make_ingredient("tomatos")
    assert find_plural_duplicates() == [[tomato, tomatoes]]


@pytest.mark.django_db
def test_find_plural_duplicates_honours_the_plural_name_override(make_ingredient):
    avocado = make_ingredient("avocado", plural_name="avocados")
    avocados = make_ingredient("avocados")
    assert find_plural_duplicates() == [[avocado, avocados]]


@pytest.mark.django_db
def test_find_plural_duplicates_matches_case_insensitively(make_ingredient):
    onion = make_ingredient("onion")
    onions = make_ingredient("Onions")
    assert find_plural_duplicates() == [[onion, onions]]


@pytest.mark.django_db
def test_find_plural_duplicates_ignores_invariant_and_lone_rows(make_ingredient):
    make_ingredient("onion")
    make_ingredient("oats")
    make_ingredient("broccoli", plural_name="broccoli")
    assert find_plural_duplicates() == []


@pytest.mark.django_db
def test_find_plural_duplicates_orders_groups_case_insensitively(make_ingredient):
    tomato = make_ingredient("tomato")
    tomatoes = make_ingredient("tomatoes")
    carrot = make_ingredient("carrot")
    carrots = make_ingredient("carrots")
    assert find_plural_duplicates() == [[carrot, carrots], [tomato, tomatoes]]


@pytest.mark.django_db
def test_search_ingredients_plurals_only_lists_both_halves_of_each_pair(make_ingredient):
    make_ingredient("onion")
    make_ingredient("onions")
    make_ingredient("carrot")
    names = [i.ingredient_name for i in search_ingredients("", plurals_only=True)]
    assert names == ["onion", "onions"]


@pytest.mark.django_db
def test_search_ingredients_plurals_only_composes_with_the_query(make_ingredient):
    make_ingredient("onion")
    make_ingredient("onions")
    make_ingredient("carrot")
    make_ingredient("carrots")
    names = [i.ingredient_name for i in search_ingredients("onio", plurals_only=True)]
    assert names == ["onion", "onions"]


@pytest.mark.django_db
def test_search_ingredients_plurals_only_composes_with_unused_only(
    make_ingredient, make_recipe, add_ingredient, user
):
    onion = make_ingredient("onion")
    make_ingredient("onions")
    recipe = make_recipe(owner=user, name="Soup")
    add_ingredient(recipe=recipe, ingredient=onion)
    names = [i.ingredient_name for i in search_ingredients("", unused_only=True, plurals_only=True)]
    assert names == ["onions"]


@pytest.mark.django_db
def test_search_ingredients_plurals_only_defaults_off(make_ingredient):
    make_ingredient("carrot")
    assert [i.ingredient_name for i in search_ingredients("")] == ["carrot"]


@pytest.mark.django_db
def test_merge_plural_records_the_deleted_name_as_the_plural(make_ingredient):
    """The whole point: the spelling you merge away lands in the plural column."""
    apple = make_ingredient("apple")
    apples = make_ingredient("apples")
    merge_plural_ingredients(singular_id=apple.pk, plural_id=apples.pk)
    apple.refresh_from_db()
    assert apple.plural_name == "apples"
    assert not Ingredient.objects.filter(pk=apples.pk).exists()


@pytest.mark.django_db
def test_merge_plural_stores_a_spelling_the_rule_would_not_produce(make_ingredient):
    """`chili` pluralises to `chilies` by rule; the stored spelling has to win."""
    chili = make_ingredient("chili")
    chilis = make_ingredient("chilis")
    merge_plural_ingredients(singular_id=chili.pk, plural_id=chilis.pk)
    chili.refresh_from_db()
    assert chili.plural == "chilis"


@pytest.mark.django_db
def test_merge_plural_carries_recipes_across(make_ingredient, make_recipe, add_ingredient, user):
    apple = make_ingredient("apple")
    apples = make_ingredient("apples")
    recipe = make_recipe(owner=user, name="Crumble")
    iir = add_ingredient(recipe=recipe, ingredient=apples)
    merge_plural_ingredients(singular_id=apple.pk, plural_id=apples.pk)
    iir.refresh_from_db()
    assert iir.ingredient_id == apple.pk


@pytest.mark.django_db
def test_merge_plural_carries_substitute_references_across(
    make_ingredient, make_recipe, add_ingredient, user
):
    apple = make_ingredient("apple")
    apples = make_ingredient("apples")
    pear = make_ingredient("pear")
    recipe = make_recipe(owner=user, name="Crumble")
    iir = add_ingredient(recipe=recipe, ingredient=pear, substitute=apples)
    merge_plural_ingredients(singular_id=apple.pk, plural_id=apples.pk)
    iir.refresh_from_db()
    assert iir.substitute_id == apple.pk


@pytest.mark.django_db
def test_merge_plural_overwrites_an_existing_override(make_ingredient):
    """Merging is an explicit statement about the plural, so it wins."""
    apple = make_ingredient("apple", plural_name="appels")
    apples = make_ingredient("apples")
    merge_plural_ingredients(singular_id=apple.pk, plural_id=apples.pk)
    apple.refresh_from_db()
    assert apple.plural_name == "apples"


@pytest.mark.django_db
def test_merge_plural_rejects_an_unknown_singular(make_ingredient):
    apples = make_ingredient("apples")
    with pytest.raises(ObjectDoesNotExist):
        merge_plural_ingredients(singular_id=0, plural_id=apples.pk)


@pytest.mark.django_db
def test_merge_plural_rejects_an_unknown_plural(make_ingredient):
    apple = make_ingredient("apple")
    with pytest.raises(ObjectDoesNotExist):
        merge_plural_ingredients(singular_id=apple.pk, plural_id=0)


@pytest.mark.django_db
def test_merge_plural_rejects_merging_a_row_into_itself(make_ingredient):
    apple = make_ingredient("apple")
    with pytest.raises(ValueError):
        merge_plural_ingredients(singular_id=apple.pk, plural_id=apple.pk)
    apple.refresh_from_db()
    assert apple.plural_name == ""


@pytest.mark.django_db
def test_suggest_singular_picks_the_half_that_pluralises_into_the_other(make_ingredient):
    apple = make_ingredient("apple")
    apples = make_ingredient("apples")
    assert suggest_singular([apples, apple]) == apple.pk


@pytest.mark.django_db
def test_suggest_singular_falls_back_to_the_first_when_the_rule_disagrees(make_ingredient):
    """`chili` pluralises to `chilies`, so neither name derives the other."""
    chili = make_ingredient("chili")
    chilis = make_ingredient("chilis")
    assert suggest_singular([chili, chilis]) == chili.pk


def test_suggest_singular_of_nothing_is_none():
    assert suggest_singular([]) is None
