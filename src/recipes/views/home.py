from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.vary import vary_on_headers

from recipes.services.recipe_search import (
    SEARCH_FIELDS,
    cuisine_choices,
    matched_ingredients,
    search_recipes,
    tag_choices,
)
from recipes.views._search import search_from, search_querystring
from recipes.views._types import AuthedRequest

PAGE_SIZE = 20

# The element the box's active search swaps (#32).
RESULTS_TARGET = "search-results"


@vary_on_headers("HX-Request", "HX-Target")
def home(request: AuthedRequest) -> HttpResponse:
    """List the signed-in user's recipes, searched, filtered and a page at a time."""
    search = search_from(request.GET)
    page = Paginator(search_recipes(owner=request.user, search=search), PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    recipes = list(page.object_list)
    matches = matched_ingredients(recipes=recipes, search=search)
    list_url = reverse("recipes:home")
    context = {
        "search": search,
        "search_qs": search_querystring(search),
        "page_obj": page,
        "latest_recipe_list": recipes,
        "rows": [(recipe, matches.get(recipe.pk, [])) for recipe in recipes],
        "prev_page_url": (
            list_url + search_querystring(search, page=page.previous_page_number())
            if page.has_previous()
            else ""
        ),
        "next_page_url": (
            list_url + search_querystring(search, page=page.next_page_number())
            if page.has_next()
            else ""
        ),
    }
    if request.htmx and request.htmx.target == RESULTS_TARGET:
        return render(request, "recipes/partials/_search_results.html", context)
    context |= {
        "search_fields": SEARCH_FIELDS,
        "cuisines": cuisine_choices(request.user),
        "tags": tag_choices(request.user),
    }
    return render(request, "recipes/home.html", context)
