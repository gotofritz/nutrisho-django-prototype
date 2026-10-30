"""Tests for merging, splitting and bulk-deleting steps (issue #18)."""

import pytest

from recipes.models import Recipe, Step


@pytest.fixture
def recipe(make_recipe, user):
    """Recipe."""
    return make_recipe(owner=user, name="Bulk Recipe")


@pytest.fixture
def steps(recipe, add_step):
    """Four steps, the first two titled."""
    return [
        add_step(recipe=recipe, text="Boil water.", title="Stock"),
        add_step(recipe=recipe, text="Add salt.", title="Seasoning"),
        add_step(recipe=recipe, text="Stir."),
        add_step(recipe=recipe, text="Serve."),
    ]


def _texts(recipe: Recipe) -> list[str]:
    return list(
        Step.objects.filter(recipe=recipe)
        .order_by("index_in_sequence")
        .values_list("step_text", flat=True)
    )


def _indexes(recipe: Recipe) -> list[int]:
    return list(
        Step.objects.filter(recipe=recipe)
        .order_by("index_in_sequence")
        .values_list("index_in_sequence", flat=True)
    )


# --- selection UI ---


@pytest.mark.django_db
def test_step_display_has_a_selection_checkbox(auth_client, recipe, steps):
    """Each displayed step carries a checkbox posting its id."""
    content = auth_client.get(f"/recipes/{recipe.pk}/steps/{steps[0].pk}/").content.decode()
    assert 'class="step-select"' in content
    assert f'name="step_ids" value="{steps[0].pk}"' in content


@pytest.mark.django_db
def test_recipe_page_has_the_bulk_panel(auth_client, recipe, steps):
    """The recipe page offers Merge and Delete for the checked steps."""
    content = auth_client.get(f"/recipes/{recipe.pk}/").content.decode()
    assert 'id="steps-block"' in content
    assert f"/recipes/{recipe.pk}/steps/merge/" in content
    assert f"/recipes/{recipe.pk}/steps/bulk-delete/" in content
    assert 'hx-include=".step-select:checked"' in content


# --- bulk delete ---


@pytest.mark.django_db
def test_bulk_delete_removes_the_selection_and_compacts(auth_client, recipe, steps):
    """Non-contiguous deletes leave a gapless sequence."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/bulk-delete/",
        {"step_ids": [steps[0].pk, steps[2].pk]},
    )
    assert response.status_code == 200
    assert _texts(recipe) == ["Add salt.", "Serve."]
    assert _indexes(recipe) == [0, 1]


@pytest.mark.django_db
def test_bulk_delete_returns_the_steps_block(auth_client, recipe, steps):
    """The response replaces the whole steps block."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/bulk-delete/", {"step_ids": [steps[0].pk]}
    )
    content = response.content.decode()
    assert 'id="steps-block"' in content
    assert "Add salt." in content
    assert "Boil water." not in content


@pytest.mark.django_db
def test_bulk_delete_with_nothing_selected_is_422(auth_client, recipe, steps):
    """An empty selection deletes nothing and says why."""
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/bulk-delete/")
    assert response.status_code == 422
    assert "Select at least one step" in response.content.decode()
    assert len(_texts(recipe)) == len(steps)


@pytest.mark.django_db
def test_bulk_delete_with_invalid_ids_is_422(auth_client, recipe, steps):
    """Non-numeric ids are refused."""
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/bulk-delete/", {"step_ids": ["x"]})
    assert response.status_code == 422
    assert len(_texts(recipe)) == len(steps)


@pytest.mark.django_db
def test_bulk_delete_ignores_other_recipes_steps(auth_client, user, make_recipe, add_step, recipe):
    """A step id from another recipe is not deleted."""
    other = make_recipe(owner=user, name="Other")
    foreign = add_step(recipe=other, text="Keep me")
    mine = add_step(recipe=recipe, text="Delete me")
    auth_client.post(
        f"/recipes/{recipe.pk}/steps/bulk-delete/", {"step_ids": [foreign.pk, mine.pk]}
    )
    assert Step.objects.filter(pk=foreign.pk).exists()
    assert not Step.objects.filter(pk=mine.pk).exists()


@pytest.mark.django_db
def test_bulk_delete_other_owners_recipe_is_404(auth_client, other_user, make_recipe, add_step):
    """Recipes stay owner-scoped."""
    theirs = make_recipe(owner=other_user, name="Theirs")
    step = add_step(recipe=theirs, text="x")
    response = auth_client.post(f"/recipes/{theirs.pk}/steps/bulk-delete/", {"step_ids": [step.pk]})
    assert response.status_code == 404
    assert Step.objects.filter(pk=step.pk).exists()


@pytest.mark.django_db
def test_bulk_delete_requires_post(auth_client, recipe):
    """GET is not allowed."""
    response = auth_client.get(f"/recipes/{recipe.pk}/steps/bulk-delete/")
    assert response.status_code == 405


# --- merge ---


@pytest.mark.django_db
def test_merge_appends_texts_into_the_highest_step(auth_client, recipe, steps):
    """Non-contiguous steps merge into the one highest up the page."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/merge/",
        # posted out of page order on purpose: page order decides, not post order
        {"step_ids": [steps[3].pk, steps[1].pk]},
    )
    assert response.status_code == 200
    assert _texts(recipe) == ["Boil water.", "Add salt. Serve.", "Stir."]
    assert _indexes(recipe) == [0, 1, 2]
    survivor = Step.objects.get(pk=steps[1].pk)
    assert survivor.step_text == "Add salt. Serve."
    assert not Step.objects.filter(pk=steps[3].pk).exists()


@pytest.mark.django_db
def test_merge_keeps_the_highest_steps_title(auth_client, recipe, steps):
    """The higher step wins: its title stays, the others' go."""
    auth_client.post(f"/recipes/{recipe.pk}/steps/merge/", {"step_ids": [steps[0].pk, steps[1].pk]})
    survivor = Step.objects.get(pk=steps[0].pk)
    assert survivor.step_title == "Stock"
    assert survivor.step_text == "Boil water. Add salt."


@pytest.mark.django_db
def test_merge_returns_the_steps_block(auth_client, recipe, steps):
    """The response replaces the whole steps block."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/merge/", {"step_ids": [steps[2].pk, steps[3].pk]}
    )
    content = response.content.decode()
    assert 'id="steps-block"' in content
    assert "Stir. Serve." in content


@pytest.mark.django_db
def test_merge_needs_two_steps(auth_client, recipe, steps):
    """One step cannot be merged with itself."""
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/merge/", {"step_ids": [steps[0].pk]})
    assert response.status_code == 422
    assert "Select at least two steps" in response.content.decode()
    assert len(_texts(recipe)) == len(steps)


@pytest.mark.django_db
def test_merge_counts_only_this_recipes_steps(auth_client, user, make_recipe, add_step, recipe):
    """A foreign id does not make up the two-step minimum."""
    other = make_recipe(owner=user, name="Other")
    foreign = add_step(recipe=other, text="Foreign")
    mine = add_step(recipe=recipe, text="Mine")
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/merge/", {"step_ids": [mine.pk, foreign.pk]}
    )
    assert response.status_code == 422
    assert Step.objects.get(pk=foreign.pk).step_text == "Foreign"


@pytest.mark.django_db
def test_merge_with_invalid_ids_is_422(auth_client, recipe, steps):
    """Non-numeric ids are refused."""
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/merge/", {"step_ids": ["x", "y"]})
    assert response.status_code == 422


@pytest.mark.django_db
def test_merge_refuses_text_longer_than_a_step_holds(auth_client, recipe, add_step):
    """Merging must not truncate: an over-long result writes nothing."""
    long_text = "a" * 500  # a step holds 512 characters
    first = add_step(recipe=recipe, text=long_text)
    second = add_step(recipe=recipe, text="b" * 20)
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/merge/", {"step_ids": [first.pk, second.pk]}
    )
    assert response.status_code == 422
    assert "too long" in response.content.decode()
    assert Step.objects.filter(recipe=recipe).count() == 2
    assert Step.objects.get(pk=first.pk).step_text == long_text


# --- split ---


@pytest.mark.django_db
def test_step_edit_has_a_split_button(auth_client, recipe, steps):
    """Editing an existing step offers Split at cursor."""
    content = auth_client.get(f"/recipes/{recipe.pk}/steps/{steps[0].pk}/edit/").content.decode()
    assert f"/recipes/{recipe.pk}/steps/{steps[0].pk}/split/" in content


@pytest.mark.django_db
def test_step_add_has_no_split_button(auth_client, recipe):
    """An unsaved draft has nothing to split."""
    content = auth_client.post(f"/recipes/{recipe.pk}/steps/add/").content.decode()
    assert "/split/" not in content


@pytest.mark.django_db
def test_split_inserts_the_tail_right_after(auth_client, recipe, steps):
    """The text after the cursor becomes a new step directly below."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/{steps[1].pk}/split/",
        {"step_title": "Seasoning", "step_text": "Add salt. Taste it.", "split_at": "9"},
    )
    assert response.status_code == 200
    assert _texts(recipe) == ["Boil water.", "Add salt.", "Taste it.", "Stir.", "Serve."]
    assert _indexes(recipe) == [0, 1, 2, 3, 4]
    head = Step.objects.get(pk=steps[1].pk)
    tail = Step.objects.get(recipe=recipe, step_text="Taste it.")
    assert head.step_title == "Seasoning"
    assert tail.step_title == ""


@pytest.mark.django_db
def test_split_saves_the_edited_text_and_title(auth_client, recipe, steps):
    """Split works on what is in the form, not what was saved."""
    auth_client.post(
        f"/recipes/{recipe.pk}/steps/{steps[3].pk}/split/",
        {"step_title": "Finish", "step_text": "Plate up. Serve hot.", "split_at": "10"},
    )
    head = Step.objects.get(pk=steps[3].pk)
    assert (head.step_title, head.step_text) == ("Finish", "Plate up.")
    assert _texts(recipe)[-1] == "Serve hot."


@pytest.mark.django_db
def test_split_returns_the_steps_block_retargeted(auth_client, recipe, steps):
    """The form targets its own row; a split changes two, so it retargets."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/{steps[0].pk}/split/",
        {"step_text": "Boil water. Then cool.", "split_at": "12"},
    )
    assert response["HX-Retarget"] == "#steps-block"
    assert response["HX-Reswap"] == "outerHTML"
    assert 'id="steps-block"' in response.content.decode()


@pytest.mark.django_db
def test_split_normalises_crlf_before_using_the_cursor(auth_client, recipe, steps):
    """The cursor counts a new line as one character, as the textarea does."""
    auth_client.post(
        f"/recipes/{recipe.pk}/steps/{steps[0].pk}/split/",
        {"step_text": "Line one\r\nLine two\r\nLine three", "split_at": "17"},
    )
    assert Step.objects.get(pk=steps[0].pk).step_text == "Line one\nLine two"
    assert _texts(recipe)[1] == "Line three"


@pytest.mark.parametrize("split_at", ["0", "2", "10", "11", "", "x"])
@pytest.mark.django_db
def test_split_refuses_a_senseless_cursor(auth_client, recipe, steps, split_at):
    """A cursor in the first or last word (or nowhere) re-renders the form."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/{steps[0].pk}/split/",
        {"step_text": "Boil water", "split_at": split_at},
    )
    assert response.status_code == 422
    content = response.content.decode()
    assert "<form" in content
    assert "between two words" in content
    assert len(_texts(recipe)) == len(steps)
    assert Step.objects.get(pk=steps[0].pk).step_text == "Boil water."


@pytest.mark.django_db
def test_split_with_an_invalid_form_re_renders_it(auth_client, recipe, steps):
    """Form errors win over the split."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/{steps[0].pk}/split/",
        {"step_text": "", "split_at": "0"},
    )
    assert response.status_code == 422
    assert "<form" in response.content.decode()
    assert len(_texts(recipe)) == len(steps)


@pytest.mark.django_db
def test_split_other_recipes_step_is_404(auth_client, user, make_recipe, add_step, recipe):
    """The step must belong to the recipe in the URL."""
    other = make_recipe(owner=user, name="Other")
    foreign = add_step(recipe=other, text="Boil water")
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/{foreign.pk}/split/",
        {"step_text": "Boil water", "split_at": "5"},
    )
    assert response.status_code == 404
