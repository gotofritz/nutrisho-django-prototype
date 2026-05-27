from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.vary import vary_on_headers

from recipes.models import IngredientInRecipe, Recipe
from recipes.views._types import AuthedRequest


def _get_recipe_nav(recipe_id: int, user: AbstractBaseUser) -> dict[str, int]:
    qs = Recipe.objects.filter(owner=user)
    order_by = "id"
    try:
        prev_id = qs.filter(id__lt=recipe_id).order_by(f"-{order_by}")[0].id
    except IndexError:
        prev_id = qs.order_by(f"-{order_by}")[0].id
    try:
        next_id = qs.filter(id__gt=recipe_id).order_by(order_by)[0].id
    except IndexError:
        next_id = qs.order_by(order_by)[0].id
    return {"prev_id": prev_id, "next_id": next_id}


@vary_on_headers("HX-Request")
def recipe(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    recipe = get_object_or_404(
        Recipe.objects.prefetch_related(
            "step",
            Prefetch(
                "ingredients_group__ingredient",
                queryset=IngredientInRecipe.objects.select_related(
                    "ingredient", "ingredient_group"
                ),
            ),
        ),
        id=recipe_id,
        owner=request.user,
    )
    template = (
        "recipes/partials/_recipe_content.html"
        if request.htmx  # type: ignore[attr-defined]  # django-htmx middleware
        else "recipes/recipe.html"
    )
    return render(
        request,
        template,
        {"recipe": recipe, "nav": _get_recipe_nav(recipe_id, request.user)},
    )
