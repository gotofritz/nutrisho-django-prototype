"""Tests for the recipe search service (#32)."""

import pytest
from django.db import IntegrityError, transaction

from recipes.models import Cuisine, Recipe, Tag
from recipes.services.recipe_search import (
    RecipeSearch,
    cuisine_choices,
    matched_ingredients,
    search_recipes,
    tag_choices,
)


def _names(recipes) -> list[str]:
    return [str(r.recipe_name) for r in recipes]


@pytest.fixture
def pantry(user, make_recipe, make_ingredient, add_ingredient):
    """Three recipes: one with aubergine, one with pasta, one with both."""
    aubergine = make_ingredient("aubergine")
    pasta = make_ingredient("spaghetti")
    onion = make_ingredient("onion")
    curry = make_recipe(owner=user, name="Aubergine curry")
    add_ingredient(recipe=curry, ingredient=aubergine)
    add_ingredient(recipe=curry, ingredient=onion)
    carbonara = make_recipe(owner=user, name="Carbonara")
    carbonara.short_description = "Roman pasta with egg"
    carbonara.save()
    add_ingredient(recipe=carbonara, ingredient=pasta)
    norma = make_recipe(owner=user, name="Pasta alla norma")
    add_ingredient(recipe=norma, ingredient=aubergine)
    add_ingredient(recipe=norma, ingredient=pasta)
    make_recipe(owner=user, name="Plain rice")
    return {"curry": curry, "carbonara": carbonara, "norma": norma}


# --- Plain-text columns -----------------------------------------------------------


@pytest.mark.django_db
def test_saving_stores_the_plain_text_of_name_and_description(user):
    """The tag-free forms are kept in step with the typed ones."""
    recipe = Recipe.objects.create(
        recipe_name="<u>Ragù</u> <s>old</s>", short_description="<b>Rich</b><br>slow", owner=user
    )
    recipe.refresh_from_db()
    assert recipe.plain_name == "Ragù old"
    assert recipe.plain_description == "Rich slow"


@pytest.mark.django_db
def test_saving_one_field_also_updates_its_plain_text(user):
    """`save(update_fields=[...])`, as the inline editor does, keeps the plain column too."""
    recipe = Recipe.objects.create(recipe_name="Soup", owner=user)
    recipe.recipe_name = "<u>Stew</u>"
    recipe.short_description = "<i>Hearty</i>"
    recipe.save(update_fields=["recipe_name"])
    recipe.refresh_from_db()
    assert recipe.plain_name == "Stew"
    assert recipe.short_description == ""
    assert recipe.plain_description == ""
    recipe.short_description = "<i>Hearty</i>"
    recipe.save(update_fields=["short_description"])
    recipe.refresh_from_db()
    assert recipe.plain_description == "Hearty"


@pytest.mark.django_db
def test_names_differing_only_by_markup_clash(user):
    """`Foo` and `<u>Foo</u>` read the same, so one owner cannot have both."""
    Recipe.objects.create(recipe_name="Foo", owner=user)
    with pytest.raises(IntegrityError), transaction.atomic():
        Recipe.objects.create(recipe_name="<u>Foo</u>", owner=user)


@pytest.mark.django_db
def test_other_owners_may_reuse_a_name(user, other_user):
    """Uniqueness is still per owner."""
    Recipe.objects.create(recipe_name="Foo", owner=user)
    Recipe.objects.create(recipe_name="<u>Foo</u>", owner=other_user)
    assert Recipe.objects.filter(plain_name="Foo").count() == 2


# --- Matching -----------------------------------------------------------------------


@pytest.mark.django_db
def test_no_query_lists_every_recipe_newest_first(user, pantry):
    """An empty search is the plain list, in the order the home page always used."""
    results = _names(search_recipes(owner=user, search=RecipeSearch()))
    assert results == ["Plain rice", "Pasta alla norma", "Carbonara", "Aubergine curry"]


@pytest.mark.django_db
def test_any_word_matches_and_both_words_rank_first(user, pantry):
    """`aubergine pasta` finds recipes with either; the one with both comes first."""
    results = _names(search_recipes(owner=user, search=RecipeSearch(query="Aubergine pasta")))
    assert results[0] == "Pasta alla norma"
    assert set(results) == {"Pasta alla norma", "Aubergine curry", "Carbonara"}


@pytest.mark.django_db
def test_a_title_match_ranks_above_a_match_elsewhere(user, make_recipe):
    """Among recipes matching as many words, a hit in the title wins over a newer one."""
    make_recipe(owner=user, name="Pasta bake")
    lasagne = make_recipe(owner=user, name="Lasagne")
    lasagne.short_description = "Sheets of pasta in layers"
    lasagne.save()
    results = _names(search_recipes(owner=user, search=RecipeSearch(query="pasta")))
    assert results == ["Pasta bake", "Lasagne"]


@pytest.mark.django_db
def test_the_description_is_searched(user, pantry):
    """A word only in the blurb still finds the recipe."""
    results = _names(search_recipes(owner=user, search=RecipeSearch(query="roman")))
    assert results == ["Carbonara"]


@pytest.mark.django_db
def test_ingredients_are_searched(user, pantry):
    """What can I cook with the aubergine in the fridge?"""
    results = _names(search_recipes(owner=user, search=RecipeSearch(query="aubergine")))
    assert set(results) == {"Aubergine curry", "Pasta alla norma"}


@pytest.mark.django_db
def test_a_plural_query_finds_the_singular_ingredient(user, pantry):
    """`aubergines` finds the `aubergine` row."""
    search = RecipeSearch(query="aubergines", field="ingredient")
    assert set(_names(search_recipes(owner=user, search=search))) == {
        "Aubergine curry",
        "Pasta alla norma",
    }


@pytest.mark.django_db
def test_a_substitute_counts_as_an_ingredient(user, make_recipe, make_ingredient, add_ingredient):
    """A recipe that takes courgette in place of aubergine can use the aubergine."""
    recipe = make_recipe(owner=user, name="Ratatouille")
    add_ingredient(
        recipe=recipe,
        ingredient=make_ingredient("courgette"),
        substitute=make_ingredient("aubergine"),
    )
    search = RecipeSearch(query="aubergine", field="ingredient")
    assert _names(search_recipes(owner=user, search=search)) == ["Ratatouille"]


@pytest.mark.django_db
def test_the_ingredient_field_ignores_titles(user, pantry):
    """Looking in ingredients only skips `Pasta` in a title without pasta in it."""
    recipe = Recipe.objects.get(recipe_name="Plain rice")
    recipe.recipe_name = "Rice not pasta"
    recipe.save()
    search = RecipeSearch(query="pasta spaghetti", field="ingredient")
    assert set(_names(search_recipes(owner=user, search=search))) == {
        "Carbonara",
        "Pasta alla norma",
    }


@pytest.mark.django_db
def test_the_name_field_looks_at_titles_only(user, pantry):
    """Looking in titles skips ingredients and descriptions."""
    search = RecipeSearch(query="pasta", field="name")
    assert _names(search_recipes(owner=user, search=search)) == ["Pasta alla norma"]


@pytest.mark.django_db
def test_markup_is_not_searched(user, make_recipe):
    """Since #17 titles can hold `<u>`; a query for `u` must not match the tag."""
    make_recipe(owner=user, name="<u>Ragout</u>")
    make_recipe(owner=user, name="<u>Soup</u>")
    assert _names(search_recipes(owner=user, search=RecipeSearch(query="u"))) == []
    assert _names(search_recipes(owner=user, search=RecipeSearch(query="ragout"))) == [
        "<u>Ragout</u>"
    ]


@pytest.mark.django_db
def test_words_match_from_their_start(user, make_recipe):
    """`pea` finds `Pea soup`, not `Chickpea stew`."""
    make_recipe(owner=user, name="Pea soup")
    make_recipe(owner=user, name="Chickpea stew")
    assert _names(search_recipes(owner=user, search=RecipeSearch(query="pea"))) == ["Pea soup"]


@pytest.mark.django_db
def test_matching_ignores_case(user, make_recipe):
    """`SOUP` finds `Pea soup`."""
    make_recipe(owner=user, name="Pea soup")
    assert _names(search_recipes(owner=user, search=RecipeSearch(query="SOUP"))) == ["Pea soup"]


@pytest.mark.django_db
def test_a_phrase_must_appear_as_typed(user, make_recipe):
    """`"pea soup"` finds the phrase, not each word on its own."""
    make_recipe(owner=user, name="Pea soup")
    make_recipe(owner=user, name="Soup with peas")
    search = RecipeSearch(query='"pea soup"')
    assert _names(search_recipes(owner=user, search=search)) == ["Pea soup"]


@pytest.mark.django_db
def test_an_excluded_word_rules_recipes_out(user, pantry):
    """`pasta -aubergine` keeps Carbonara, drops Norma."""
    search = RecipeSearch(query="pasta -aubergine")
    assert _names(search_recipes(owner=user, search=search)) == ["Carbonara"]


@pytest.mark.django_db
def test_exclusions_alone_filter_the_whole_list(user, pantry):
    """`-aubergine` lists every recipe without it."""
    search = RecipeSearch(query="-aubergine")
    assert _names(search_recipes(owner=user, search=search)) == ["Plain rice", "Carbonara"]


@pytest.mark.django_db
def test_tags_and_cuisines_are_searched(user, make_recipe):
    """A tag or a cuisine node at any level finds the recipe."""
    area = Cuisine.objects.create(cuisine="testarea")
    region = Cuisine.objects.create(cuisine="testland", parent=area)
    tagged = make_recipe(owner=user, name="Tagged")
    Tag.objects.create(tag="weeknight").recipes.add(tagged)
    placed = make_recipe(owner=user, name="Placed")
    placed.cuisine = region
    placed.save()
    assert _names(search_recipes(owner=user, search=RecipeSearch(query="weeknight"))) == ["Tagged"]
    assert _names(search_recipes(owner=user, search=RecipeSearch(query="testarea"))) == ["Placed"]


@pytest.mark.django_db
def test_another_users_recipes_are_never_found(user, other_user, make_recipe):
    """Search is owner-scoped like the list."""
    make_recipe(owner=other_user, name="Secret soup")
    assert list(search_recipes(owner=user, search=RecipeSearch(query="soup"))) == []


@pytest.mark.django_db
def test_each_recipe_appears_once(user, make_recipe, make_ingredient, add_ingredient):
    """A recipe matching through several ingredients is not repeated."""
    recipe = make_recipe(owner=user, name="Tomato soup")
    add_ingredient(recipe=recipe, ingredient=make_ingredient("tomato"))
    add_ingredient(recipe=recipe, ingredient=make_ingredient("tomato puree"))
    search = RecipeSearch(query="tomatoes")
    assert _names(search_recipes(owner=user, search=search)) == ["Tomato soup"]


# --- Filters ------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_cuisine_filter_includes_everything_below_the_node(user, make_recipe):
    """Filtering on an area finds recipes on its regions and subregions too."""
    area = Cuisine.objects.create(cuisine="testarea")
    region = Cuisine.objects.create(cuisine="testland", parent=area)
    sub = Cuisine.objects.create(cuisine="testshire", parent=region)
    other = Cuisine.objects.create(cuisine="elsewhere")
    for name, cuisine in [("On area", area), ("On region", region), ("On sub", sub)]:
        recipe = make_recipe(owner=user, name=name)
        recipe.cuisine = cuisine
        recipe.save()
    elsewhere = make_recipe(owner=user, name="Elsewhere")
    elsewhere.cuisine = other
    elsewhere.save()
    make_recipe(owner=user, name="Nowhere")
    found = _names(search_recipes(owner=user, search=RecipeSearch(cuisine_id=area.pk)))
    assert set(found) == {"On area", "On region", "On sub"}
    found = _names(search_recipes(owner=user, search=RecipeSearch(cuisine_id=region.pk)))
    assert set(found) == {"On region", "On sub"}


@pytest.mark.django_db
def test_the_tag_filter_narrows_the_list(user, pantry):
    """Only recipes carrying the tag."""
    tag = Tag.objects.create(tag="favourite")
    tag.recipes.add(pantry["curry"], pantry["norma"])
    search = RecipeSearch(query="pasta", tag_id=tag.pk)
    assert _names(search_recipes(owner=user, search=search)) == ["Pasta alla norma"]


@pytest.mark.django_db
def test_the_cuisine_choices_are_the_users_nodes_and_their_ancestors(user, other_user, make_recipe):
    """The filter offers every node with one of the user's recipes on it or below it."""
    area = Cuisine.objects.create(cuisine="testarea")
    region = Cuisine.objects.create(cuisine="testland", parent=area)
    Cuisine.objects.create(cuisine="unused", parent=area)
    secret = Cuisine.objects.create(cuisine="secretland")
    recipe = make_recipe(owner=user, name="Mine")
    recipe.cuisine = region
    recipe.save()
    theirs = make_recipe(owner=other_user, name="Theirs")
    theirs.cuisine = secret
    theirs.save()
    assert [c.path for c in cuisine_choices(user)] == ["testarea", "testarea.testland"]


@pytest.mark.django_db
def test_the_tag_choices_are_the_tags_on_the_users_recipes(user, other_user, make_recipe):
    """Global or private, a tag is offered once one of the user's recipes carries it."""
    mine = make_recipe(owner=user, name="Mine")
    theirs = make_recipe(owner=other_user, name="Theirs")
    Tag.objects.create(tag="weeknight").recipes.add(mine)
    Tag.objects.create(tag="Batch", owner=user).recipes.add(mine)
    Tag.objects.create(tag="unused")
    Tag.objects.create(tag="theirs", owner=other_user).recipes.add(theirs)
    assert [str(t.tag) for t in tag_choices(user)] == ["Batch", "weeknight"]


# --- What matched -------------------------------------------------------------------


@pytest.mark.django_db
def test_matched_ingredients_names_what_the_query_found(user, pantry):
    """The list shows which ingredients answered the query."""
    search = RecipeSearch(query="aubergines pasta spaghetti")
    found = matched_ingredients(recipes=list(pantry.values()), search=search)
    assert found == {
        pantry["curry"].pk: ["aubergine"],
        pantry["carbonara"].pk: ["spaghetti"],
        pantry["norma"].pk: ["aubergine", "spaghetti"],
    }


@pytest.mark.django_db
def test_matched_ingredients_is_empty_without_a_query(user, pantry):
    """Nothing typed, nothing to show, no query run."""
    assert matched_ingredients(recipes=list(pantry.values()), search=RecipeSearch()) == {}


@pytest.mark.django_db
def test_matched_ingredients_is_empty_when_looking_in_titles(user, pantry):
    """A title-only search found nothing through ingredients."""
    search = RecipeSearch(query="aubergine", field="name")
    assert matched_ingredients(recipes=list(pantry.values()), search=search) == {}
