from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from recipes.forms.step_form import StepForm
from recipes.models import Recipe, Step


@require_GET
def recipe_step_display(request: HttpRequest, recipe_id: int, step_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    return render(
        request,
        "recipes/partials/_step_display.html",
        {"recipe": recipe, "step": step},
    )


@require_GET
def recipe_step_edit(request: HttpRequest, recipe_id: int, step_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    form = StepForm(instance=step)
    return render(
        request,
        "recipes/partials/_step_edit.html",
        {"recipe": recipe, "step": step, "form": form},
    )


@require_POST
def recipe_step_save(request: HttpRequest, recipe_id: int, step_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    form = StepForm(data=request.POST, instance=step)
    if form.is_valid():
        form.save()
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
def recipe_step_delete(request: HttpRequest, recipe_id: int, step_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    deleted_index = step.index_in_sequence
    step.delete()
    remaining = Step.objects.filter(recipe=recipe, index_in_sequence__gt=deleted_index).order_by(
        "index_in_sequence"
    )
    for s in remaining:
        s.index_in_sequence -= 1
        s.save()
    return HttpResponse("")


@require_POST
def recipe_step_add(request: HttpRequest, recipe_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    next_index = Step.objects.filter(recipe=recipe).count()
    step = Step.objects.create(recipe=recipe, step_text="New step", index_in_sequence=next_index)
    form = StepForm(instance=step)
    return render(
        request,
        "recipes/partials/_step_edit.html",
        {"recipe": recipe, "step": step, "form": form},
    )
