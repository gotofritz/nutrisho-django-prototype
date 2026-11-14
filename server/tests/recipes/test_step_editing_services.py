"""Tests for the step merge and split services (#77), called without a request."""

import pytest
from django.core.exceptions import ObjectDoesNotExist

from recipes.models import Recipe, Step
from recipes.models.recipe import PROSE_MAX_LENGTH
from recipes.services.step_editing import StepEditError, merge_steps, split_step


@pytest.fixture
def recipe(user, make_recipe) -> Recipe:
    """A recipe owned by the test user."""
    return make_recipe(owner=user, name="Steps")


def _steps(recipe: Recipe) -> list[tuple[str, str, int]]:
    return [
        (s.step_title, s.step_text, s.index_in_sequence)
        for s in Step.objects.filter(recipe=recipe).order_by("index_in_sequence")
    ]


# --- merge_steps ---


@pytest.mark.django_db
def test_merge_appends_onto_the_highest_step(recipe, add_step):
    """The highest step keeps its title; the others' texts follow in page order."""
    first = add_step(recipe=recipe, text="Boil.", title="Pasta")
    middle = add_step(recipe=recipe, text="Chop.")
    last = add_step(recipe=recipe, text="Drain.", title="Gone")
    survivor = merge_steps(recipe=recipe, step_ids=[last.pk, first.pk])
    assert survivor.pk == first.pk
    assert _steps(recipe) == [("Pasta", "Boil. Drain.", 0), ("", "Chop.", 1)]
    assert middle.pk in Step.objects.values_list("pk", flat=True)


@pytest.mark.django_db
def test_merge_needs_two_steps_of_the_recipe(recipe, add_step, other_user, make_recipe):
    """Foreign ids do not count towards the two."""
    mine = add_step(recipe=recipe, text="Boil.")
    foreign = add_step(recipe=make_recipe(owner=other_user, name="Theirs"), text="Chop.")
    with pytest.raises(StepEditError, match="at least two steps"):
        merge_steps(recipe=recipe, step_ids=[mine.pk, foreign.pk])
    assert _steps(recipe) == [("", "Boil.", 0)]


@pytest.mark.django_db
def test_merge_refuses_a_result_too_long_for_a_step(recipe, add_step):
    """An over-long merge writes nothing rather than truncating."""
    long_text = "a" * (PROSE_MAX_LENGTH - 10)
    first = add_step(recipe=recipe, text=long_text)
    second = add_step(recipe=recipe, text="b" * 20)
    with pytest.raises(StepEditError, match="too long"):
        merge_steps(recipe=recipe, step_ids=[first.pk, second.pk])
    assert _steps(recipe) == [("", long_text, 0), ("", "b" * 20, 1)]


# --- split_step ---


@pytest.mark.django_db
def test_split_puts_the_tail_right_below(recipe, add_step):
    """The head keeps the title; the tail becomes an untitled step below it."""
    add_step(recipe=recipe, text="Boil.")
    step = add_step(recipe=recipe, text="old", title="old")
    add_step(recipe=recipe, text="Serve.")
    step.step_title = "Season"
    split_step(recipe=recipe, step=step, text="Add salt. Taste it.", at=9)
    assert _steps(recipe) == [
        ("", "Boil.", 0),
        ("Season", "Add salt.", 1),
        ("", "Taste it.", 2),
        ("", "Serve.", 3),
    ]


@pytest.mark.django_db
def test_split_counts_the_cursor_after_folding_crlf(recipe, add_step):
    """A form post's CRLF counts as one character, as in the textarea."""
    step = add_step(recipe=recipe, text="old")
    split_step(recipe=recipe, step=step, text="Line one\r\nLine two\r\nLine three", at=17)
    assert _steps(recipe) == [("", "Line one\nLine two", 0), ("", "Line three", 1)]


@pytest.mark.django_db
def test_split_counts_the_cursor_in_the_text_as_typed(recipe, add_step):
    """The offset is into the textarea's text, leading blanks included."""
    step = add_step(recipe=recipe, text="old")
    split_step(recipe=recipe, step=step, text="   Boil. Drain.", at=9)
    assert [text.strip() for _, text, _ in _steps(recipe)] == ["Boil.", "Drain."]


@pytest.mark.django_db
@pytest.mark.parametrize("at", [-1, 0, 2, 10])
def test_split_refuses_a_cursor_that_leaves_a_half_blank(recipe, add_step, at):
    """The cursor must sit after the first word and before the last."""
    step = add_step(recipe=recipe, text="One two.")
    with pytest.raises(StepEditError, match="between two words"):
        split_step(recipe=recipe, step=step, text="One two.", at=at)
    assert _steps(recipe) == [("", "One two.", 0)]


@pytest.mark.django_db
def test_split_of_a_deleted_step_is_refused_as_missing(recipe, add_step):
    """A step deleted since the form opened cannot be split."""
    step = add_step(recipe=recipe, text="One two.")
    Step.objects.filter(pk=step.pk).delete()
    with pytest.raises(ObjectDoesNotExist):
        split_step(recipe=recipe, step=step, text="One two.", at=4)
    assert _steps(recipe) == []
