from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from recipes.forms.field_forms import EDITABLE_RECIPE_FIELDS, RecipeFieldForm
from recipes.models import Recipe
from recipes.views._types import AuthedRequest


def _require_editable_field(field_name: str) -> None:
    if field_name not in EDITABLE_RECIPE_FIELDS:
        raise Http404(f"Field '{field_name}' is not editable")


@require_GET
def recipe_field_display(request: AuthedRequest, recipe_id: int, field_name: str) -> HttpResponse:
    _require_editable_field(field_name)
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
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
def recipe_field_edit(request: AuthedRequest, recipe_id: int, field_name: str) -> HttpResponse:
    _require_editable_field(field_name)
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    form = RecipeFieldForm(field_name, instance=recipe)
    return render(
        request,
        "recipes/partials/_field_edit.html",
        {"recipe": recipe, "field_name": field_name, "form": form},
    )


@require_POST
def recipe_field_save(request: AuthedRequest, recipe_id: int, field_name: str) -> HttpResponse:
    _require_editable_field(field_name)
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    form = RecipeFieldForm(field_name, data=request.POST, instance=recipe)
    if form.is_valid():
        try:
            with transaction.atomic():
                locked = list(Recipe.objects.filter(pk=recipe.pk).select_for_update().values("pk"))
                if not locked:
                    return HttpResponse("", status=404)
                form.save(commit=False)
                recipe.save(update_fields=[field_name])
        except IntegrityError:
            form.add_error(field_name, "You already have a recipe with that name.")
        else:
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
