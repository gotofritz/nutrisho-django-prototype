from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from recipes.forms.field_forms import EDITABLE_RECIPE_FIELDS, RecipeFieldForm
from recipes.models import Recipe


def _require_editable_field(field_name: str) -> None:
    if field_name not in EDITABLE_RECIPE_FIELDS:
        raise Http404(f"Field '{field_name}' is not editable")


@require_GET
def recipe_field_display(request: HttpRequest, recipe_id: int, field_name: str) -> HttpResponse:
    _require_editable_field(field_name)
    recipe = get_object_or_404(Recipe, id=recipe_id)
    return render(
        request,
        "recipes/partials/_field_display.html",
        {
            "recipe": recipe,
            "field_name": field_name,
            "value": getattr(recipe, field_name),
        },
    )


@require_GET
def recipe_field_edit(request: HttpRequest, recipe_id: int, field_name: str) -> HttpResponse:
    _require_editable_field(field_name)
    recipe = get_object_or_404(Recipe, id=recipe_id)
    form = RecipeFieldForm(field_name, instance=recipe)
    return render(
        request,
        "recipes/partials/_field_edit.html",
        {"recipe": recipe, "field_name": field_name, "form": form},
    )


@require_POST
def recipe_field_save(request: HttpRequest, recipe_id: int, field_name: str) -> HttpResponse:
    _require_editable_field(field_name)
    recipe = get_object_or_404(Recipe, id=recipe_id)
    form = RecipeFieldForm(field_name, data=request.POST, instance=recipe)
    if form.is_valid():
        form.save()
        recipe.refresh_from_db()
        return render(
            request,
            "recipes/partials/_field_display.html",
            {
                "recipe": recipe,
                "field_name": field_name,
                "value": getattr(recipe, field_name),
            },
        )
    return render(
        request,
        "recipes/partials/_field_edit.html",
        {"recipe": recipe, "field_name": field_name, "form": form},
    )
