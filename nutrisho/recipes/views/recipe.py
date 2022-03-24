from django.shortcuts import get_object_or_404, render

from recipes.models import Recipe


def recipe(request, recipe_id):
    recipe = get_object_or_404(Recipe, pk=recipe_id)
    return render(request, "recipes/recipe.html", {"recipe": recipe})
