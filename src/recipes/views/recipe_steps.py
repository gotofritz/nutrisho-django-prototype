from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from recipes.forms.step_form import StepForm
from recipes.models import Recipe, Step
from recipes.utils.sequencing import insert_at_index, move_in_sequence, remove_and_compact
from recipes.views._types import AuthedRequest


@require_GET
def recipe_step_display(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    return render(
        request,
        "recipes/partials/_step_display.html",
        {"recipe": recipe, "step": step},
    )


@require_GET
def recipe_step_edit(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    form = StepForm(instance=step)
    return render(
        request,
        "recipes/partials/_step_edit.html",
        {"recipe": recipe, "step": step, "form": form},
    )


@require_POST
def recipe_step_save(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    form = StepForm(data=request.POST, instance=step)
    if form.is_valid():
        with transaction.atomic():
            if not Step.objects.select_for_update().filter(pk=step.pk, recipe=recipe).exists():
                return HttpResponse("", status=404)
            form.save(commit=False)
            step.save(update_fields=["step_text"])
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
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    remove_and_compact(siblings=Step.objects.filter(recipe=recipe), instance=step)
    return HttpResponse("")


@require_POST
def recipe_step_move_up(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    move_in_sequence(siblings=Step.objects.filter(recipe=recipe), instance=step, direction="up")
    return render(request, "recipes/partials/_steps_list.html", {"recipe": recipe})


@require_POST
def recipe_step_move_down(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    move_in_sequence(siblings=Step.objects.filter(recipe=recipe), instance=step, direction="down")
    return render(request, "recipes/partials/_steps_list.html", {"recipe": recipe})


@require_POST
def recipe_step_add(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Render a blank step form; no row is created until create succeeds."""
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    return render(
        request,
        "recipes/partials/_step_edit.html",
        {"recipe": recipe, "step": None, "form": StepForm()},
    )


@require_POST
def recipe_step_create(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    form = StepForm(data=request.POST)
    if form.is_valid():
        with transaction.atomic():
            locked = list(Recipe.objects.filter(pk=recipe.pk).select_for_update().values("pk"))
            if not locked:
                return HttpResponse("", status=404)
            step = form.save(commit=False)
            step.recipe = recipe
            insert_at_index(
                siblings=Step.objects.filter(recipe=recipe),
                instance=step,
                requested_index=request.POST.get("position"),
                lock_parent=None,
            )
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
