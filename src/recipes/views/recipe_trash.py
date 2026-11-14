"""The trash: deleted recipes, restored with Undo or from the list, or deleted for good (#75)."""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from recipes.services.recipe_trash import purge_recipe, restore_recipe, trashed_recipes
from recipes.views._auth import trashed_recipe
from recipes.views._types import AuthedRequest


def _go(request: AuthedRequest, url: str) -> HttpResponse:
    """Navigate to `url`: HX-Redirect for htmx, a plain redirect otherwise."""
    if request.htmx:
        response = HttpResponse()
        response["HX-Redirect"] = url
        return response
    return redirect(url)


@require_GET
def trash(request: AuthedRequest) -> HttpResponse:
    """List the signed-in user's trashed recipes."""
    return render(
        request,
        "recipes/trash.html",
        {"recipes": list(trashed_recipes(owner=request.user))},
    )


@require_POST
def recipe_restore(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Take a recipe out of the trash and open it; the toast's Undo posts here."""
    recipe = restore_recipe(trashed_recipe(request=request, recipe_id=recipe_id))
    messages.success(request, f"Restored “{recipe.plain_name}”.")
    return _go(request, recipe.get_absolute_url())


@require_POST
def recipe_purge(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Delete a trashed recipe for good and go back to the trash."""
    recipe = trashed_recipe(request=request, recipe_id=recipe_id)
    name = recipe.plain_name
    purge_recipe(recipe)
    messages.success(request, f"Deleted “{name}” for good.")
    return _go(request, reverse("recipes:trash"))
