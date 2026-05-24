from django.shortcuts import get_object_or_404, render

from recipes.forms.recipe_edit_form import RecipeEditForm
from recipes.models import Recipe


def _get_recipe_nav(recipe_id):
    order_by = "id"
    try:
        prev_id = Recipe.objects.filter(id__lt=recipe_id).order_by(f"-{order_by}")[0].id
    except IndexError:
        prev_id = Recipe.objects.all().order_by(f"-{order_by}")[0].id
    try:
        next_id = Recipe.objects.filter(id__gt=recipe_id).order_by(order_by)[0].id
    except IndexError:
        next_id = Recipe.objects.all().order_by(order_by)[0].id
    return {"prev_id": prev_id, "next_id": next_id}


def recipe(request, recipe_id):
    recipe = get_object_or_404(Recipe, id=recipe_id)
    template = "recipes/partials/_recipe_content.html" if request.htmx else "recipes/recipe.html"
    return render(
        request,
        template,
        {"recipe": recipe, "nav": _get_recipe_nav(recipe_id)},
    )


def recipe_edit(request, recipe_id):
    recipe = get_object_or_404(Recipe, id=recipe_id)
    form_data = {}
    if request.POST:
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
        {
            "recipe": recipe,
            "form": form,
            "nav": _get_recipe_nav(recipe_id),
        },
    )
