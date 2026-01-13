from django.shortcuts import render

from recipes.models import Recipe


def home(request):
    latest_recipe_list = Recipe.objects.order_by("-created_date")
    context = {
        "latest_recipe_list": latest_recipe_list,
    }
    return render(request, "recipes/home.html", context)
