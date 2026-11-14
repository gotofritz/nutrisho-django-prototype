"""Download all of a user's recipes, and import a file of them (#78)."""

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from recipes.forms.import_form import RecipeImportForm
from recipes.services.recipe_export import export_recipes
from recipes.services.recipe_import import import_recipes
from recipes.views._types import AuthedRequest


@require_GET
def recipe_export(request: AuthedRequest) -> HttpResponse:
    """The signed-in user's recipes, trash included, as a Nutrisho file to save."""
    response = JsonResponse(
        export_recipes(owner=request.user), json_dumps_params={"ensure_ascii": False, "indent": 2}
    )
    filename = f"nutrisho-recipes-{timezone.localdate().isoformat()}.json"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_http_methods(["GET", "POST"])
def recipe_import(request: AuthedRequest) -> HttpResponse:
    """The import and export page; a valid upload is imported and its recipes listed."""
    form = RecipeImportForm()
    result = None
    if request.method == "POST":
        form = RecipeImportForm(data=request.POST, files=request.FILES)
        if form.is_valid():
            result = import_recipes(owner=request.user, batch=form.cleaned_data["file"])
            form = RecipeImportForm()
    return render(request, "recipes/transfer.html", {"form": form, "result": result})
