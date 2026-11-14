from typing import Literal

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from recipes.forms.ingredient_forms import IngredientGroupForm, IngredientInRecipeForm
from recipes.models import IngredientGroup, IngredientInRecipe, Recipe
from recipes.services.ingredient_groups import (
    GroupDeletion,
    GroupNameError,
    ReassignError,
    create_group,
    create_row,
    delete_group,
    delete_row,
    move_row,
    reassign_rows,
    rename_group,
    save_row,
)
from recipes.services.name_resolution import suggest_ingredient_names
from recipes.services.recipe_contents import with_ingredients, with_rows
from recipes.utils.sequencing import move_in_sequence
from recipes.views._announce import announce
from recipes.views._auth import owned_recipe
from recipes.views._types import AuthedRequest


def _reassign_select_oob(recipe: Recipe, request: AuthedRequest) -> str:
    """OOB fragment that keeps the reassign <select> in sync after group mutations."""
    return render_to_string(
        "recipes/partials/_reassign_select_oob.html", {"recipe": recipe}, request=request
    )


def _groups_list(request: AuthedRequest, recipe: Recipe, *, error: str = "") -> HttpResponse:
    """The whole ingredients column; with an error, a 422 that shows it."""
    return render(
        request,
        "recipes/partials/_groups_list.html",
        {"recipe": with_ingredients(recipe), "error": error},
        status=422 if error else 200,
    )


def _whole_groups_list(request: AuthedRequest, recipe: Recipe) -> HttpResponse:
    """`_groups_list` swapped over the whole column, for a request aimed at one group."""
    response = _groups_list(request, recipe)
    response["HX-Retarget"] = "#groups-list"
    response["HX-Reswap"] = "innerHTML"
    return response


@require_GET
def ingredient_suggest(request: AuthedRequest) -> HttpResponse:
    """`<option>`s for the editor's ingredient datalist: the top matches for the typed text.

    Both name inputs share the datalist and send their own value, under their
    own name. Suggestions are the signed-in user's vocabulary, and the editor
    only ever edits their own recipes.
    """
    text = request.GET.get("ingredient_name") or request.GET.get("substitute_name", "")
    return render(
        request,
        "recipes/partials/_ingredient_suggestions.html",
        {"names": suggest_ingredient_names(text, owner=request.user)},
    )


@require_GET
def recipe_ingredient_display(request: AuthedRequest, recipe_id: int, iir_id: int) -> HttpResponse:
    """Show a ingredient."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    iir = get_object_or_404(IngredientInRecipe, id=iir_id, ingredient_group__recipe=recipe)
    return render(
        request,
        "recipes/partials/_ingredient_display.html",
        {"recipe": recipe, "iir": iir},
    )


@require_GET
def recipe_ingredient_edit(request: AuthedRequest, recipe_id: int, iir_id: int) -> HttpResponse:
    """Show the ingredient edit form."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    iir = get_object_or_404(IngredientInRecipe, id=iir_id, ingredient_group__recipe=recipe)
    form = IngredientInRecipeForm(instance=iir, owner=recipe.owner)
    return render(
        request,
        "recipes/partials/_ingredient_edit.html",
        {
            "recipe": recipe,
            "iir": iir,
            "form": form,
        },
    )


def _typed_names(form: IngredientInRecipeForm) -> dict[str, str]:
    return {
        "ingredient_name": form.cleaned_data["ingredient_name"],
        "substitute_name": form.cleaned_data["substitute_name"],
    }


@require_POST
def recipe_ingredient_save(request: AuthedRequest, recipe_id: int, iir_id: int) -> HttpResponse:
    """Save a ingredient."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    iir = get_object_or_404(IngredientInRecipe, id=iir_id, ingredient_group__recipe=recipe)
    form = IngredientInRecipeForm(data=request.POST, instance=iir, owner=recipe.owner)
    if form.is_valid():
        try:
            save_row(recipe=recipe, row=form.save(commit=False), **_typed_names(form))
        except ObjectDoesNotExist:
            return HttpResponse("", status=404)
        iir.refresh_from_db()
        return render(
            request,
            "recipes/partials/_ingredient_display.html",
            {"recipe": recipe, "iir": iir},
        )
    return render(
        request,
        "recipes/partials/_ingredient_edit.html",
        {
            "recipe": recipe,
            "iir": iir,
            "form": form,
        },
    )


@require_POST
def recipe_ingredient_delete(request: AuthedRequest, recipe_id: int, iir_id: int) -> HttpResponse:
    """Delete a ingredient."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    get_object_or_404(IngredientInRecipe, id=iir_id, ingredient_group__recipe=recipe)
    deletion = delete_row(recipe=recipe, row_id=iir_id)
    if deletion is None:
        return HttpResponse("")
    if not deletion.group_pruned:
        return announce(HttpResponse(""), "Ingredient deleted.")
    # The row swap alone would leave an empty group block on the page, and the
    # reassign <select> would still offer the group that just went.
    response = HttpResponse(
        f'<div id="group-block-{deletion.group_id}" hx-swap-oob="delete"></div>'
        + _reassign_select_oob(recipe, request)
    )
    return announce(response, "Ingredient deleted.")


@require_POST
def recipe_ingredient_add(request: AuthedRequest, recipe_id: int, group_id: int) -> HttpResponse:
    """Render a blank ingredient form; no row is created until create succeeds."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    return render(
        request,
        "recipes/partials/_ingredient_edit.html",
        {
            "recipe": recipe,
            "group": group,
            "iir": None,
            "form": IngredientInRecipeForm(owner=recipe.owner),
        },
    )


@require_POST
def recipe_ingredient_create(request: AuthedRequest, recipe_id: int, group_id: int) -> HttpResponse:
    """Create a ingredient."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    form = IngredientInRecipeForm(data=request.POST, owner=recipe.owner)
    if form.is_valid():
        try:
            iir = create_row(
                recipe=recipe,
                group_id=group_id,
                row=form.save(commit=False),
                position=request.POST.get("position"),
                **_typed_names(form),
            )
        except ObjectDoesNotExist:
            return HttpResponse("", status=404)
        return render(
            request,
            "recipes/partials/_ingredient_display.html",
            {"recipe": recipe, "iir": iir},
        )
    return render(
        request,
        "recipes/partials/_ingredient_edit.html",
        {
            "recipe": recipe,
            "group": group,
            "iir": None,
            "form": form,
        },
    )


@require_POST
def recipe_ingredient_move(
    request: AuthedRequest, recipe_id: int, iir_id: int, direction: Literal["up", "down"]
) -> HttpResponse:
    """Move a ingredient up or down within its group."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    iir = get_object_or_404(IngredientInRecipe, id=iir_id, ingredient_group__recipe=recipe)
    group = move_row(recipe=recipe, row_id=iir_id, direction=direction)
    if group is None or group.pk != iir.ingredient_group_id:
        # Gone or reassigned meanwhile: the page's copy of its group is stale.
        return _whole_groups_list(request, recipe)
    return render(
        request, "recipes/partials/_iir_list.html", {"recipe": recipe, "group": with_rows(group)}
    )


@require_GET
def recipe_group_display(request: AuthedRequest, recipe_id: int, group_id: int) -> HttpResponse:
    """Show a group."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    return render(
        request,
        "recipes/partials/_group_display.html",
        {"recipe": recipe, "group": group},
    )


@require_GET
def recipe_group_edit(request: AuthedRequest, recipe_id: int, group_id: int) -> HttpResponse:
    """Show the group edit form."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    form = IngredientGroupForm(instance=group)
    return render(
        request,
        "recipes/partials/_group_edit.html",
        {"recipe": recipe, "group": group, "form": form},
    )


@require_POST
def recipe_group_save(request: AuthedRequest, recipe_id: int, group_id: int) -> HttpResponse:
    """Save a group."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    form = IngredientGroupForm(data=request.POST, instance=group)
    if form.is_valid():
        try:
            group = rename_group(
                recipe=recipe, group_id=group_id, name=form.cleaned_data["group_name"]
            )
        except ObjectDoesNotExist:
            return HttpResponse("", status=404)
        except GroupNameError as exc:
            form.add_error("group_name", str(exc))
        else:
            content = render_to_string(
                "recipes/partials/_group_display.html",
                {"recipe": recipe, "group": group},
                request=request,
            )
            return HttpResponse(content + _reassign_select_oob(recipe, request))
    return render(
        request,
        "recipes/partials/_group_edit.html",
        {"recipe": recipe, "group": group, "form": form},
    )


@require_POST
def recipe_group_delete(request: AuthedRequest, recipe_id: int, group_id: int) -> HttpResponse:
    """Delete a group and its ingredients, unless it is the recipe's last group.

    The form hides Delete for the last group, so only a stale page asks for
    that, and gets the block back.
    """
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    outcome = delete_group(recipe=recipe, group_id=group_id)
    if outcome is GroupDeletion.KEPT_LAST:
        response = render(
            request,
            "recipes/partials/_group_block.html",
            {"recipe": recipe, "group": with_rows(group)},
        )
        return announce(response, "A recipe keeps at least one group, so this one stayed.")
    response = HttpResponse(_reassign_select_oob(recipe, request))
    if outcome is GroupDeletion.MISSING:
        return response
    return announce(response, "Group deleted.")


@require_POST
def recipe_group_move(
    request: AuthedRequest, recipe_id: int, group_id: int, direction: Literal["up", "down"]
) -> HttpResponse:
    """Move a group up or down."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    move_in_sequence(
        siblings=IngredientGroup.objects.filter(recipe=recipe), instance=group, direction=direction
    )
    return _groups_list(request, recipe)


@require_POST
def recipe_group_add(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Render a blank group form; no row is created until create succeeds."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    return render(
        request,
        "recipes/partials/_group_edit.html",
        {"recipe": recipe, "group": None, "form": IngredientGroupForm()},
    )


@require_POST
def recipe_group_create(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Create a group."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    form = IngredientGroupForm(data=request.POST)
    if form.is_valid():
        try:
            group = create_group(
                recipe=recipe,
                name=form.cleaned_data["group_name"],
                position=request.POST.get("position"),
            )
        except ObjectDoesNotExist:
            return HttpResponse("", status=404)
        except GroupNameError as exc:
            form.add_error("group_name", str(exc))
        else:
            content = render_to_string(
                "recipes/partials/_group_block.html",
                {"recipe": recipe, "group": group},
                request=request,
            )
            return HttpResponse(content + _reassign_select_oob(recipe, request))
    return render(
        request,
        "recipes/partials/_group_edit.html",
        {"recipe": recipe, "group": None, "form": form},
    )


@require_POST
def recipe_ingredient_reassign(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Move ingredients into another group."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    raw_ids = request.POST.getlist("ingredient_ids")
    if not raw_ids:
        return _groups_list(request, recipe)
    try:
        row_ids = [int(i) for i in raw_ids]
    except ValueError, TypeError:
        return _groups_list(request, recipe, error="Invalid ingredient IDs.")

    raw_target = request.POST.get("target_group", "")
    target_group_id: int | None = None
    if raw_target != "new":
        try:
            target_group_id = int(raw_target)
        except ValueError, TypeError:
            return _groups_list(request, recipe, error="Invalid group.")

    try:
        reassign_rows(
            recipe=recipe,
            row_ids=row_ids,
            target_group_id=target_group_id,
            new_group_name=request.POST.get("new_group_name", ""),
        )
    except ReassignError as exc:
        return _groups_list(request, recipe, error=str(exc))
    return _groups_list(request, recipe)
