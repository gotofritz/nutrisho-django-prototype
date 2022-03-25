from django.shortcuts import get_object_or_404, render

from recipes.models import Recipe


def recipe(request, recipe_id):
    recipe = get_object_or_404(Recipe, pk=recipe_id)
    return render(request, "recipes/recipe.html", {"recipe": recipe})


def recipe_edit(request, recipe_id):
    debug = {}
    recipe = get_object_or_404(Recipe, pk=recipe_id)
    if request.POST:
        debug = "YES"
        recipe.name = request.POST["recipe.name"]
        recipe.short_description = request.POST["recipe.short_description"]
        recipe.save()
    return render(request, "recipes/edit.html", {"recipe": recipe, "debug": debug})
