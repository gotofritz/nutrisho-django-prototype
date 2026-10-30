from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from recipes.forms.step_form import StepForm
from recipes.models import Recipe, Step
from recipes.utils.sequencing import (
    insert_at_index,
    move_in_sequence,
    remove_and_compact,
    remove_many_and_compact,
)
from recipes.utils.step_text import join_step_texts, split_step_text
from recipes.views._types import AuthedRequest

_STEPS_BLOCK = "recipes/partials/_steps_block.html"
_SPLIT_REFUSED = "Put the cursor between two words to split the step."


@require_GET
def recipe_step_display(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    """Show a step."""
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    return render(
        request,
        "recipes/partials/_step_display.html",
        {"recipe": recipe, "step": step},
    )


@require_GET
def recipe_step_edit(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    """Show the step edit form."""
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
    """Save a step."""
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    form = StepForm(data=request.POST, instance=step)
    if form.is_valid():
        with transaction.atomic():
            if not Step.objects.select_for_update().filter(pk=step.pk, recipe=recipe).exists():
                return HttpResponse("", status=404)
            form.save(commit=False)
            step.save(update_fields=["step_title", "step_text"])
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
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    remove_and_compact(siblings=Step.objects.filter(recipe=recipe), instance=step)
    return HttpResponse("")


@require_POST
def recipe_step_move_up(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    """Move a step up."""
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    move_in_sequence(siblings=Step.objects.filter(recipe=recipe), instance=step, direction="up")
    return render(request, "recipes/partials/_steps_list.html", {"recipe": recipe})


@require_POST
def recipe_step_move_down(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    """Move a step down."""
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
    """Create a step."""
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
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    step_ids = _selected_step_ids(request)
    if step_ids is None:
        return _steps_block(request, recipe=recipe, error="Invalid step IDs.", status=422)
    removed = remove_many_and_compact(siblings=Step.objects.filter(recipe=recipe), pks=step_ids)
    if not removed:
        return _steps_block(
            request, recipe=recipe, error="Select at least one step to delete.", status=422
        )
    return _steps_block(request, recipe=recipe)


@require_POST
def recipe_steps_merge(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Append the checked steps to the highest one up the page.

    The highest step wins: it keeps its title and other fields, and the texts of
    the rest are appended to its own in page order, however far apart they are.
    """
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    step_ids = _selected_step_ids(request)
    if step_ids is None:
        return _steps_block(request, recipe=recipe, error="Invalid step IDs.", status=422)
    with transaction.atomic():
        steps = list(
            Step.objects.select_for_update()
            .filter(recipe=recipe, id__in=step_ids)
            .order_by("index_in_sequence")
        )
        if len(steps) < 2:
            return _steps_block(
                request, recipe=recipe, error="Select at least two steps to merge.", status=422
            )
        survivor, *rest = steps
        # Validate through the form so the merge obeys the same limits as an edit.
        form = StepForm(
            data={
                "step_title": survivor.step_title,
                "step_text": join_step_texts([s.step_text for s in steps]),
            },
            instance=survivor,
        )
        if not form.is_valid():
            return _steps_block(
                request,
                recipe=recipe,
                error="The merged step would be too long: "
                + " ".join(form.errors.get("step_text", [])),
                status=422,
            )
        form.save(commit=False)
        survivor.save(update_fields=["step_text"])
        remove_many_and_compact(
            siblings=Step.objects.filter(recipe=recipe), pks=[s.pk for s in rest]
        )
    return _steps_block(request, recipe=recipe)


@require_POST
def recipe_step_split(request: AuthedRequest, recipe_id: int, step_id: int) -> HttpResponse:
    """Split the step being edited in two at the cursor (``split_at``).

    Works on the form as typed: the text before the cursor, with the title,
    stays in this step; the text after becomes a new untitled step right below.
    """
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    step = get_object_or_404(Step, id=step_id, recipe=recipe)
    form = StepForm(data=request.POST, instance=step)
    # The textarea counts a new line as one character; form posts send CRLF.
    text = request.POST.get("step_text", "").replace("\r\n", "\n")
    try:
        halves = split_step_text(text, at=int(request.POST.get("split_at", "")))
    except ValueError:
        halves = None
    if not form.is_valid() or halves is None:
        return render(
            request,
            "recipes/partials/_step_edit.html",
            {
                "recipe": recipe,
                "step": step,
                "form": form,
                "split_error": "" if form.errors else _SPLIT_REFUSED,
            },
            status=422,
        )
    head, tail = halves
    with transaction.atomic():
        rows = list(
            Step.objects.select_for_update().filter(recipe=recipe).order_by("index_in_sequence")
        )
        position = next((i for i, row in enumerate(rows) if row.pk == step.pk), None)
        if position is None:
            return HttpResponse("", status=404)
        form.save(commit=False)
        step.step_text = head
        step.save(update_fields=["step_title", "step_text"])
        insert_at_index(
            siblings=Step.objects.filter(recipe=recipe),
            instance=Step(recipe=recipe, step_text=tail),
            requested_index=str(position + 1),
        )
    response = _steps_block(request, recipe=recipe)
    # The form targets its own row; a split changes two, so the block goes.
    response["HX-Retarget"] = "#steps-block"
    response["HX-Reswap"] = "outerHTML"
    return response
