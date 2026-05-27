from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from recipes.forms.field_forms import RecipeFieldForm
from recipes.models import Recipe


@require_http_methods(["GET", "POST"])
def recipe_new(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = RecipeFieldForm("recipe_name", data=request.POST)
        if form.is_valid():
            owner = User.objects.filter(pk=2).first() or User.objects.first()
            recipe = Recipe(owner=owner, recipe_name=form.cleaned_data["recipe_name"])
            recipe.save()
            return redirect(recipe.get_absolute_url())
        return render(request, "recipes/recipe_new.html", {"form": form})
    form = RecipeFieldForm("recipe_name")
    return render(request, "recipes/recipe_new.html", {"form": form})


@require_POST
def recipe_delete(request: HttpRequest, recipe_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    recipe.delete()
    response = HttpResponse("")
    response["HX-Redirect"] = "/recipes/"
    return response
