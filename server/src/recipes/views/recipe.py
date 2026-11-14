from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Prefetch
from django.db.models.functions import Lower
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.vary import vary_on_headers

from recipes.models import Recipe, Tag
from recipes.services.recipe_contents import ingredients_prefetch
from recipes.services.recipe_search import RecipeSearch, search_recipes
from recipes.utils.scaling import parse_servings, scale_factor
from recipes.views._search import search_from, search_querystring
from recipes.views._types import AuthedRequest
from recipes.views.home import PAGE_SIZE


def _get_recipe_nav(recipe_id: int, user: AbstractBaseUser, search: RecipeSearch) -> dict:
    """Prev/next through the list the user came from, wrapping at both ends (#32).

    The list is `search`'s results, in the order the home page shows them; a
    recipe outside them (edited since, or a hand-typed URL) walks the whole list.
    """
    ids = list(search_recipes(owner=user, search=search).values_list("id", flat=True))
    if recipe_id not in ids:
        search = RecipeSearch()
        ids = list(search_recipes(owner=user, search=search).values_list("id", flat=True))
    i = ids.index(recipe_id)
    return {
        "prev_id": ids[i - 1],
        "next_id": ids[(i + 1) % len(ids)],
        "query": search_querystring(search),
        "list_url": reverse("recipes:home") + search_querystring(search, page=i // PAGE_SIZE + 1),
        "search": search,
    }


@vary_on_headers("HX-Request")
def recipe(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Show a recipe, to read unless ?edit=1 asks to edit it (#58).

    Read mode leaves every editing control out of the sheet, so a tap while
    scrolling on a tablet opens nothing. The partial endpoints never set
    `reading`, so the lines they return are always editable.
    """
    recipe = get_object_or_404(
        Recipe.objects.live()
        .select_related("cuisine__parent__parent")
        .prefetch_related(
            "steps",
            Prefetch("tags", queryset=Tag.objects.order_by(Lower("tag"), "tag")),
            ingredients_prefetch(),
        ),
        id=recipe_id,
        owner=request.user,
    )
    # ?servings=N scales the page only; nothing is written back (#36).
    target = parse_servings(request.GET.get("servings"))
    scale = scale_factor(servings=int(recipe.servings), target=target)
    template = "recipes/partials/_recipe_content.html" if request.htmx else "recipes/recipe.html"
    nav = _get_recipe_nav(recipe_id, request.user, search_from(request.GET))
    # The mode toggle keeps the search, so previous and next still walk the same list.
    read_url = recipe.get_absolute_url() + nav["query"]
    edit_url = f"{recipe.get_absolute_url()}?edit=1{nav['query'].replace('?', '&', 1)}"
    return render(
        request,
        template,
        {
            "recipe": recipe,
            "nav": nav,
            "search": nav["search"],
            "scale": scale,
            "target_servings": target if scale else None,
            "reading": request.GET.get("edit") != "1",
            "read_url": read_url,
            "edit_url": edit_url,
        },
    )
