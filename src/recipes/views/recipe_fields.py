from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from recipes.forms.field_forms import EDITABLE_RECIPE_FIELDS, RecipeFieldForm
from recipes.services.recipe_metadata import DuplicateRecipeNameError, save_field
from recipes.views._auth import owned_recipe
from recipes.views._types import AuthedRequest


def _require_editable_field(field_name: str) -> None:
    if field_name not in EDITABLE_RECIPE_FIELDS:
        msg = f"Field '{field_name}' is not editable"
        raise Http404(msg)


@require_GET
def recipe_field_display(request: AuthedRequest, recipe_id: int, field_name: str) -> HttpResponse:
    """Show a field."""
    _require_editable_field(field_name)
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
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
    """Show the field edit form."""
    _require_editable_field(field_name)
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    form = RecipeFieldForm(field_name, instance=recipe)
    return render(
        request,
        "recipes/partials/_field_edit.html",
        {"recipe": recipe, "field_name": field_name, "form": form},
    )


@require_POST
def recipe_field_save(request: AuthedRequest, recipe_id: int, field_name: str) -> HttpResponse:
    """Save a field."""
    _require_editable_field(field_name)
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    form = RecipeFieldForm(field_name, data=request.POST, instance=recipe)
    if form.is_valid():
        try:
            save_field(recipe=form.save(commit=False), field_name=field_name)
        except ObjectDoesNotExist:
            return HttpResponse("", status=404)
        except DuplicateRecipeNameError as exc:
            form.add_error(field_name, str(exc))
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
