from typing import Literal

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from recipes.forms.step_form import StepForm
from recipes.models import Recipe, Step
from recipes.services.step_editing import (
    SPLIT_REFUSED,
    StepEditError,
    create_step,
    merge_steps,
    save_step,
    split_step,
)
from recipes.utils.sequencing import move_in_sequence, remove_and_compact, remove_many_and_compact
from recipes.views._announce import announce
from recipes.views._auth import owned_recipe
from recipes.views._types import AuthedRequest

_STEPS_BLOCK = "recipes/partials/_steps_block.html"


@require_GET
def recipe_step_display(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    """Show a step."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    return render(
        request,
        "recipes/partials/_step_display.html",
        {"recipe": recipe, "step": step},
    )


@require_GET
def recipe_step_edit(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    """Show the step edit form."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    form = StepForm(instance=step)
    return render(
        request,
        "recipes/partials/_step_edit.html",
        {"recipe": recipe, "step": step, "form": form},
    )


@require_POST
def recipe_step_save(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    """Save a step."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    form = StepForm(data=request.POST, instance=step)
    if form.is_valid():
        try:
            save_step(recipe=recipe, step=form.save(commit=False))
        except ObjectDoesNotExist:
            return HttpResponse("", status=404)
        step.refresh_from_db()
        return render(
            request,
            "recipes/partials/_step_display.html",
            {"recipe": recipe, "step": step},
        )
    return render(
        request,
        "recipes/partials/_step_edit.html",
        {"recipe": recipe, "step": step, "form": form},
    )


@require_POST
def recipe_step_delete(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    """Delete a step."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    remove_and_compact(siblings=Step.objects.filter(recipe=recipe), instance=step)
    return announce(HttpResponse(""), "Step deleted.")


@require_POST
def recipe_step_move(
    request: AuthedRequest, recipe_id: int, step_id: int, direction: Literal["up", "down"]
) -> HttpResponse:
    """Move a step up or down."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    move_in_sequence(
        siblings=Step.objects.filter(recipe=recipe), instance=step, direction=direction
    )
    return render(request, "recipes/partials/_steps_list.html", {"recipe": recipe})


@require_POST
def recipe_step_add(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Render a blank step form; no row is created until create succeeds."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    return render(
        request,
        "recipes/partials/_step_edit.html",
        {"recipe": recipe, "step": None, "form": StepForm()},
    )


@require_POST
def recipe_step_create(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Create a step."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    form = StepForm(data=request.POST)
    if form.is_valid():
        try:
            step = create_step(
                recipe=recipe, step=form.save(commit=False), position=request.POST.get("position")
            )
        except ObjectDoesNotExist:
            return HttpResponse("", status=404)
        return render(
            request,
            "recipes/partials/_step_display.html",
            {"recipe": recipe, "step": step},
        )
    return render(
        request,
        "recipes/partials/_step_edit.html",
        {"recipe": recipe, "step": None, "form": form},
    )


def _steps_block(
    request: AuthedRequest, *, recipe: Recipe, error: str = "", status: int = 200
) -> HttpResponse:
    return render(request, _STEPS_BLOCK, {"recipe": recipe, "error": error}, status=status)


def _selected_step_ids(request: AuthedRequest) -> list[int] | None:
    """The checked steps' ids, or None when any of them is not a number."""
    try:
        return [int(i) for i in request.POST.getlist("step_ids")]
    except ValueError, TypeError:
        return None


@require_POST
def recipe_steps_bulk_delete(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Delete every checked step."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    step_ids = _selected_step_ids(request)
    if step_ids is None:
        return _steps_block(request, recipe=recipe, error="Invalid step IDs.", status=422)
    removed = remove_many_and_compact(siblings=Step.objects.filter(recipe=recipe), pks=step_ids)
    if not removed:
        return _steps_block(
            request, recipe=recipe, error="Select at least one step to delete.", status=422
        )
    noun = "step" if removed == 1 else "steps"
    return announce(_steps_block(request, recipe=recipe), f"{removed} {noun} deleted.")


@require_POST
def recipe_steps_merge(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Append the checked steps to the highest one up the page (see `merge_steps`)."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    step_ids = _selected_step_ids(request)
    if step_ids is None:
        return _steps_block(request, recipe=recipe, error="Invalid step IDs.", status=422)
    try:
        merge_steps(recipe=recipe, step_ids=step_ids)
    except StepEditError as exc:
        return _steps_block(request, recipe=recipe, error=str(exc), status=422)
    return _steps_block(request, recipe=recipe)


@require_POST
def recipe_step_split(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    """Split the step being edited in two at the cursor, ``split_at`` (see `split_step`)."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    form = StepForm(data=request.POST, instance=step)
    split_error = ""
    if form.is_valid():
        try:
            split_step(
                recipe=recipe,
                step=step,
                text=request.POST.get("step_text", ""),
                at=int(request.POST.get("split_at", "")),
            )
        except ObjectDoesNotExist:
            return HttpResponse("", status=404)
        except StepEditError as exc:
            split_error = str(exc)
        except ValueError:  # `split_at` is not a number
            split_error = SPLIT_REFUSED
        else:
            response = _steps_block(request, recipe=recipe)
            # The form targets its own row; a split changes two, so the block goes.
            response["HX-Retarget"] = "#steps-block"
            response["HX-Reswap"] = "outerHTML"
            return response
    return render(
        request,
        "recipes/partials/_step_edit.html",
        {"recipe": recipe, "step": step, "form": form, "split_error": split_error},
        status=422,
    )
