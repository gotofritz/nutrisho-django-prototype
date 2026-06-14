from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render

from recipes.models import Recipe
from recipes.views._types import AuthedRequest


@login_required
def home(request: AuthedRequest) -> HttpResponse:
    latest_recipe_list = Recipe.objects.filter(owner=request.user).order_by("-created_date")
    return render(request, "recipes/home.html", {"latest_recipe_list": latest_recipe_list})
