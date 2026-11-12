"""Create, save, merge and split a recipe's steps (#18, moved out of the views in #77).

The text rules live in `recipes/utils/step_text.py`; these functions apply them
to the rows, keeping the sequence gap-free through `utils/sequencing.py`.
"""

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MaxLengthValidator
from django.db import transaction

from recipes.models import Recipe, Step
from recipes.models.recipe import PROSE_MAX_LENGTH
from recipes.utils.sequencing import insert_at_index, remove_many_and_compact
from recipes.utils.step_text import join_step_texts, split_step_text

SPLIT_REFUSED = "Put the cursor between two words to split the step."

# `Step.step_text` is a TextField, whose max_length binds only its form field.
_MAX_TEXT = MaxLengthValidator(PROSE_MAX_LENGTH)


class StepEditError(ValueError):
    """The merge or split cannot be done; the message says why."""


def create_step(*, recipe: Recipe, step: Step, position: str | None = None) -> Step:
    """Add `step`, its fields already set, at `position` (a page position).

    `ObjectDoesNotExist`, raised once the transaction has closed, when the
    recipe has gone.
    """
    with transaction.atomic():
        found = bool(list(Recipe.objects.filter(pk=recipe.pk).select_for_update().values("pk")))
        if found:
            step.recipe = recipe  # ty: ignore[invalid-assignment]  # FK descriptor
            insert_at_index(
                siblings=Step.objects.filter(recipe=recipe), instance=step, requested_index=position
            )
    if not found:
        msg = "The recipe has been deleted."
        raise ObjectDoesNotExist(msg)
    return step


def save_step(*, recipe: Recipe, step: Step) -> None:
    """Save `step`'s title and text.

    `ObjectDoesNotExist`, raised once the transaction has closed, when the step
    has gone.
    """
    with transaction.atomic():
        found = Step.objects.select_for_update().filter(pk=step.pk, recipe=recipe).exists()
        if found:
            step.save(update_fields=["step_title", "step_text"])
    if not found:
        msg = "The step has been deleted."
        raise ObjectDoesNotExist(msg)


def merge_steps(*, recipe: Recipe, step_ids: list[int]) -> Step:
    """Append the selected steps onto the one highest up the page; return it.

    The highest step keeps its title and other fields; the others' texts follow
    its own in page order, however far apart they are, and those steps go. Ids
    outside the recipe are ignored. The merged text obeys the same length limit
    as an edit, so an over-long merge writes nothing rather than truncating.
    """
    with transaction.atomic():
        steps = list(
            Step.objects.select_for_update()
            .filter(recipe=recipe, id__in=step_ids)
            .order_by("index_in_sequence")
        )
        if len(steps) < 2:
            msg = "Select at least two steps to merge."
            raise StepEditError(msg)
        survivor, *rest = steps
        text = join_step_texts([s.step_text for s in steps])
        try:
            _MAX_TEXT(text)
        except ValidationError as exc:
            msg = "The merged step would be too long: " + " ".join(exc.messages)
            raise StepEditError(msg) from exc
        survivor.step_text = text
        survivor.save(update_fields=["step_text"])
        remove_many_and_compact(
            siblings=Step.objects.filter(recipe=recipe), pks=[s.pk for s in rest]
        )
    return survivor


def split_step(*, recipe: Recipe, step: Step, text: str, at: int) -> Step:
    """Split `step` in two at cursor offset `at`; return the new step below it.

    `step` carries its title as typed, not yet saved, and `text` is its text as
    typed, which `at` indexes; a line break counts as one character, as in the
    textarea, so CRLF is folded to LF first. The text before the cursor, with
    the title, stays in `step`; the text after becomes a new untitled step
    right below. Raises `StepEditError` when
    either half would be blank, and `Step.DoesNotExist` when the step has gone.
    """
    halves = split_step_text(text.replace("\r\n", "\n"), at=at)
    if halves is None:
        raise StepEditError(SPLIT_REFUSED)
    head, tail = halves
    with transaction.atomic():
        rows = list(
            Step.objects.select_for_update().filter(recipe=recipe).order_by("index_in_sequence")
        )
        position = next((i for i, row in enumerate(rows) if row.pk == step.pk), None)
        if position is None:
            raise Step.DoesNotExist  # ty: ignore[unresolved-attribute]  # no Django stubs
        step.step_text = head  # ty: ignore[invalid-assignment]  # TextField descriptor
        step.save(update_fields=["step_title", "step_text"])
        new = Step(recipe=recipe, step_text=tail)
        insert_at_index(
            siblings=Step.objects.filter(recipe=recipe),
            instance=new,
            requested_index=str(position + 1),
        )
    return new
