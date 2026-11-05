"""Tests for the search box, the searchable list and prev/next order (#32)."""

import pytest

from recipes.models import Cuisine, Recipe, Tag
from recipes.views.home import PAGE_SIZE

_HTMX_RESULTS = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TARGET": "search-results"}


@pytest.fixture
def three(user, make_recipe, make_ingredient, add_ingredient):
    """Oldest to newest: an aubergine curry, a rice dish, an aubergine pasta."""
    aubergine = make_ingredient("aubergine")
    curry = make_recipe(owner=user, name="Curry")
    add_ingredient(recipe=curry, ingredient=aubergine)
    rice = make_recipe(owner=user, name="Rice")
    pasta = make_recipe(owner=user, name="Pasta")
    add_ingredient(recipe=pasta, ingredient=aubergine)
    return curry, rice, pasta


def _listed(response) -> list[str]:
    return [str(r.recipe_name) for r in response.context["latest_recipe_list"]]


# --- The list -------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_list_shows_only_matching_recipes(auth_client, three):
    """`?q=` filters the home page."""
    response = auth_client.get("/recipes/", {"q": "aubergine"})
    assert response.status_code == 200
    assert _listed(response) == ["Pasta", "Curry"]
    assert "2 recipes match" in response.content.decode()


@pytest.mark.django_db
def test_no_match_says_so(auth_client, three):
    """An empty result is explained, not shown as an empty collection."""
    response = auth_client.get("/recipes/", {"q": "durian"})
    content = response.content.decode()
    assert "No recipes match" in content
    assert "No recipes are available." not in content


@pytest.mark.django_db
def test_active_search_returns_only_the_results(auth_client, three):
    """Typing in the box swaps just the results, the way the ingredient tool searches."""
    response = auth_client.get("/recipes/", {"q": "rice"}, **_HTMX_RESULTS)
    content = response.content.decode()
    assert 'id="search-results"' in content
    assert "<html" not in content
    assert 'id="search-q"' not in content
    assert _listed(response) == ["Rice"]
    assert "HX-Request" in response["Vary"]


@pytest.mark.django_db
def test_a_boosted_visit_gets_the_whole_page(auth_client, three):
    """Submitting the box from another page navigates to the full list."""
    response = auth_client.get(
        "/recipes/", {"q": "rice"}, HTTP_HX_REQUEST="true", HTTP_HX_BOOSTED="true"
    )
    assert 'id="search-q"' in response.content.decode()


@pytest.mark.django_db
def test_the_list_has_the_advanced_search_form(auth_client, user, three):
    """The home page offers the query, where to look, cuisine and tag, prefilled."""
    cuisine = Cuisine.objects.create(cuisine="testland")
    three[0].cuisine = cuisine
    three[0].save()
    tag = Tag.objects.create(tag="weeknight")
    tag.recipe.add(three[1])
    response = auth_client.get(
        "/recipes/",
        {"q": "aubergine", "in": "ingredient", "cuisine": cuisine.pk, "tag": tag.pk},
    )
    content = response.content.decode()
    assert 'role="search"' in content
    assert 'id="search-q"' in content
    assert 'value="aubergine"' in content
    assert '<option value="ingredient" selected>' in content
    assert f'<option value="{cuisine.pk}" selected>testland</option>' in content
    assert f'<option value="{tag.pk}" selected>weeknight</option>' in content
    # The page carries its own search box, so the site-wide one is left out.
    assert 'id="site-search-q"' not in content


@pytest.mark.django_db
def test_the_filters_apply(auth_client, three):
    """Cuisine and tag narrow the list; `in=name` looks at titles only."""
    tag = Tag.objects.create(tag="weeknight")
    tag.recipe.add(three[0])
    assert _listed(auth_client.get("/recipes/", {"tag": tag.pk})) == ["Curry"]
    assert _listed(auth_client.get("/recipes/", {"q": "aubergine", "in": "name"})) == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "params",
    [{"cuisine": "abc"}, {"tag": "-1x"}, {"in": "steps"}, {"page": "lots"}, {"page": "999"}],
)
def test_malformed_parameters_are_ignored(auth_client, three, params):
    """A hand-edited URL shows a list, never an error."""
    response = auth_client.get("/recipes/", params)
    assert response.status_code == 200
    assert len(_listed(response)) == 3


@pytest.mark.django_db
def test_results_link_to_the_recipe_with_the_search(auth_client, three):
    """The recipe page needs the search to walk the same list."""
    pasta = three[2]
    content = auth_client.get("/recipes/", {"q": "aubergine"}).content.decode()
    assert f'href="/recipes/{pasta.pk}/?q=aubergine"' in content


@pytest.mark.django_db
def test_results_name_the_ingredients_that_matched(auth_client, three):
    """`with aubergine` under a result whose title does not say so."""
    content = auth_client.get("/recipes/", {"q": "aubergine"}).content.decode()
    assert "with aubergine" in content


@pytest.mark.django_db
def test_the_list_is_paginated(auth_client, user, make_recipe):
    """PAGE_SIZE recipes a page, with links that keep the search."""
    for i in range(PAGE_SIZE + 3):
        make_recipe(owner=user, name=f"Soup {i:02}")
    first = auth_client.get("/recipes/", {"q": "soup"})
    assert len(_listed(first)) == PAGE_SIZE
    content = first.content.decode()
    assert 'href="/recipes/?q=soup&amp;page=2"' in content
    assert "Page 1 of 2" in content
    second = auth_client.get("/recipes/", {"q": "soup", "page": "2"})
    assert len(_listed(second)) == 3
    assert 'href="/recipes/?q=soup"' in second.content.decode()


@pytest.mark.django_db
def test_a_short_list_has_no_page_links(auth_client, three):
    """One page, no pagination."""
    assert "Page 1 of" not in auth_client.get("/recipes/").content.decode()


@pytest.mark.django_db
def test_the_list_query_count_does_not_grow_with_the_page(
    auth_client, user, make_recipe, make_ingredient, add_ingredient, django_assert_max_num_queries
):
    """Matching ingredients come in one query for the whole page."""
    onion = make_ingredient("onion")
    for i in range(PAGE_SIZE):
        add_ingredient(recipe=make_recipe(owner=user, name=f"Soup {i}"), ingredient=onion)
    with django_assert_max_num_queries(12):
        response = auth_client.get("/recipes/", {"q": "onion soup"})
    assert len(_listed(response)) == PAGE_SIZE


# --- The site-wide box ------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("page", ["recipe", "metadata", "new", "ingredients", "cuisines"])
def test_every_page_has_the_search_box(auth_client, user, make_recipe, page):
    """The box sits at the top of every signed-in page and searches the list."""
    user.is_staff = True
    user.save()
    recipe = make_recipe(owner=user, name="Soup")
    url = {
        "recipe": f"/recipes/{recipe.pk}/",
        "metadata": f"/recipes/{recipe.pk}/metadata/",
        "new": "/recipes/new/",
        "ingredients": "/recipes/ingredients/manage/",
        "cuisines": "/recipes/cuisines/manage/",
    }[page]
    content = auth_client.get(url).content.decode()
    assert 'id="site-search-q"' in content
    assert 'action="/recipes/"' in content


@pytest.mark.django_db
def test_a_boosted_visit_to_a_recipe_keeps_the_box(auth_client, three):
    """A boosted visit renders the recipe partial, which replaces the whole body."""
    response = auth_client.get(f"/recipes/{three[0].pk}/", HTTP_HX_REQUEST="true")
    assert 'id="site-search-q"' in response.content.decode()


def test_the_login_page_has_no_search_box(client, db):
    """Nothing to search before signing in."""
    assert 'id="site-search-q"' not in client.get("/accounts/login/").content.decode()


@pytest.mark.django_db
def test_the_box_on_a_recipe_shows_the_search_it_came_from(auth_client, three):
    """Arriving from a search, the box still holds the query."""
    content = auth_client.get(f"/recipes/{three[2].pk}/", {"q": "aubergine"}).content.decode()
    assert 'id="site-search-q" name="q" value="aubergine"' in content


# --- Prev/next -------------------------------------------------------------------------


@pytest.mark.django_db
def test_prev_next_walks_the_list_order(auth_client, three):
    """Newest first, as listed: next goes down the list, prev up, wrapping."""
    curry, rice, pasta = three
    nav = auth_client.get(f"/recipes/{rice.pk}/").context["nav"]
    assert (nav["prev_id"], nav["next_id"]) == (pasta.pk, curry.pk)
    nav = auth_client.get(f"/recipes/{curry.pk}/").context["nav"]
    assert nav["next_id"] == pasta.pk


@pytest.mark.django_db
def test_prev_next_stays_within_the_search(auth_client, three):
    """From a search, prev/next skip what did not match and keep the query."""
    curry, _rice, pasta = three
    response = auth_client.get(f"/recipes/{pasta.pk}/", {"q": "aubergine"})
    nav = response.context["nav"]
    assert (nav["prev_id"], nav["next_id"]) == (curry.pk, curry.pk)
    content = response.content.decode()
    assert f'href="/recipes/{curry.pk}/?q=aubergine"' in content
    assert 'href="/recipes/?q=aubergine"' in content


@pytest.mark.django_db
def test_the_list_link_returns_to_the_recipes_page(auth_client, user, make_recipe):
    """Back to the list lands on the page the recipe is on."""
    recipes = [make_recipe(owner=user, name=f"Soup {i:02}") for i in range(PAGE_SIZE + 2)]
    oldest = recipes[0]
    nav = auth_client.get(f"/recipes/{oldest.pk}/", {"q": "soup"}).context["nav"]
    assert nav["list_url"] == "/recipes/?q=soup&page=2"


@pytest.mark.django_db
def test_a_recipe_outside_the_search_walks_the_whole_list(auth_client, three):
    """A search the recipe does not match (edited since, or typed by hand) is dropped."""
    curry, rice, pasta = three
    response = auth_client.get(f"/recipes/{rice.pk}/", {"q": "aubergine"})
    nav = response.context["nav"]
    assert (nav["prev_id"], nav["next_id"]) == (pasta.pk, curry.pk)
    assert nav["list_url"] == "/recipes/"
    assert "?q=aubergine" not in response.content.decode()


@pytest.mark.django_db
def test_the_search_survives_the_filters_in_the_query(auth_client, three):
    """Every part of the search is carried, not just the words."""
    tag = Tag.objects.create(tag="weeknight")
    tag.recipe.add(three[0], three[2])
    response = auth_client.get(
        f"/recipes/{three[2].pk}/", {"q": "aubergine", "in": "ingredient", "tag": tag.pk}
    )
    assert response.context["nav"]["query"] == f"?q=aubergine&in=ingredient&tag={tag.pk}"


@pytest.mark.django_db
def test_recipe_name_with_markup_is_found_by_its_text(auth_client, user):
    """End to end: an underlined title is found by its words, not by `u`."""
    Recipe.objects.create(recipe_name="<u>Ragout</u>", owner=user)
    assert _listed(auth_client.get("/recipes/", {"q": "ragout"})) == ["<u>Ragout</u>"]
    assert _listed(auth_client.get("/recipes/", {"q": "u"})) == []


@pytest.mark.django_db
def test_a_name_differing_only_by_markup_is_a_form_error(auth_client, user):
    """The editor refuses `<u>Foo</u>` next to `Foo`, as it refuses a second `Foo`."""
    Recipe.objects.create(recipe_name="Foo", owner=user)
    other = Recipe.objects.create(recipe_name="Bar", owner=user)
    response = auth_client.post(
        f"/recipes/{other.pk}/field/recipe_name/save/", {"recipe_name": "<u>Foo</u>"}
    )
    assert "You already have a recipe with that name." in response.content.decode()
    other.refresh_from_db()
    assert other.recipe_name == "Bar"
