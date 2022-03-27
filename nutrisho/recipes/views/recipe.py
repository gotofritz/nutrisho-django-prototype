from xmlrpc.client import Boolean
from django.shortcuts import get_object_or_404, render

from recipes.models import Recipe

from recipes.forms.recipe_edit_form import RecipeEditForm


def recipe(request, recipe_id):
    recipe = get_object_or_404(Recipe, pk=recipe_id)
    return render(request, "recipes/recipe.html", {"recipe": recipe})


def recipe_edit(request, recipe_id):
    debug = {}
    recipe = get_object_or_404(Recipe, pk=recipe_id)
    form_data = {}
    if request.POST:
        debug = "YES"
        # recipe.recipe_name = request.POST["recipe.recipe_name"]
        # recipe.short_description = request.POST["recipe.short_description"]
        # recipe.save()
        form_data = request.POST
    else:
        form_data = {
            "recipe_name": recipe.recipe_name,
            "short_description": recipe.short_description,
        }
    form = RecipeEditForm(form_data, instance=recipe)
    return render(
        request,
        "recipes/recipe.html",
        {"recipe": recipe, "form": form, "debug": debug},
    )
