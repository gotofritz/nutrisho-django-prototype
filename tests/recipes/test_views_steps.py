"""Tests for recipe step inline-edit views (Plan 004, Step 2)."""

import pytest
from django.test import Client

from recipes.models import Recipe, Step


@pytest.fixture
def auth_client(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def recipe(user, db):
    return Recipe.objects.create(recipe_name="Step Recipe", owner=user)


@pytest.fixture
def step(recipe):
    return Step.objects.create(recipe=recipe, step_text="Boil water", index_in_sequence=0)


@pytest.fixture
def two_steps(recipe):
    s1 = Step.objects.create(recipe=recipe, step_text="First step", index_in_sequence=0)
    s2 = Step.objects.create(recipe=recipe, step_text="Second step", index_in_sequence=1)
    return s1, s2


@pytest.mark.django_db
def test_step_display_get_returns_200(auth_client, recipe, step):
    response = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_step_display_no_form_elements(auth_client, recipe, step):
    response = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/")
    content = response.content.decode()
    assert "<form" not in content


@pytest.mark.django_db
def test_step_display_shows_step_text(auth_client, recipe, step):
    response = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/")
    assert step.step_text.encode() in response.content


@pytest.mark.django_db
def test_step_display_404_wrong_recipe(auth_client, user, db):
    other = Recipe.objects.create(recipe_name="Other", owner=user)
    step = Step.objects.create(recipe=other, step_text="x", index_in_sequence=0)
    recipe = Recipe.objects.create(recipe_name="Mine", owner=user)
    response = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_step_edit_get_returns_200(auth_client, recipe, step):
    response = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/edit/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_step_edit_has_form_with_value(auth_client, recipe, step):
    response = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/edit/")
    content = response.content.decode()
    assert "<form" in content
    assert step.step_text in content


@pytest.mark.django_db
def test_step_edit_cancel_button_points_to_display(auth_client, recipe, step):
    response = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/edit/")
    content = response.content.decode()
    display_url = f"/recipes/{recipe.pk}/steps/{step.pk}/"
    assert display_url in content


@pytest.mark.django_db
def test_step_save_post_valid_saves_and_returns_display(auth_client, recipe, step):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/{step.pk}/save/",
        {"step_text": "Updated step text"},
    )
    assert response.status_code == 200
    step.refresh_from_db()
    assert step.step_text == "Updated step text"
    content = response.content.decode()
    assert "<form" not in content


@pytest.mark.django_db
def test_step_save_post_invalid_returns_form(auth_client, recipe, step):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/{step.pk}/save/",
        {"step_text": ""},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "<form" in content


@pytest.mark.django_db
def test_step_delete_removes_step(auth_client, recipe, step):
    step_id = step.pk
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/{step_id}/delete/")
    assert response.status_code == 200
    assert not Step.objects.filter(pk=step_id).exists()


@pytest.mark.django_db
def test_step_delete_reorders_remaining(auth_client, recipe, two_steps):
    first, second = two_steps
    auth_client.post(f"/recipes/{recipe.pk}/steps/{first.pk}/delete/")
    second.refresh_from_db()
    assert second.index_in_sequence == 0


@pytest.mark.django_db
def test_step_add_does_not_create_step(auth_client, recipe):
    """Add only renders a blank form; the row is created on Save (create)."""
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/add/")
    assert response.status_code == 200
    assert Step.objects.filter(recipe=recipe).count() == 0


@pytest.mark.django_db
def test_step_add_form_posts_to_create_url(auth_client, recipe):
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/add/")
    assert f"/recipes/{recipe.pk}/steps/create/" in response.content.decode()


@pytest.mark.django_db
def test_step_create_valid_creates_step(auth_client, recipe):
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/create/", {"step_text": "Chop onions"})
    assert response.status_code == 200
    step = Step.objects.get(recipe=recipe)
    assert step.step_text == "Chop onions"
    assert step.index_in_sequence == 0
    assert "Chop onions" in response.content.decode()


@pytest.mark.django_db
def test_step_create_appends_after_existing(auth_client, recipe, two_steps):
    auth_client.post(f"/recipes/{recipe.pk}/steps/create/", {"step_text": "Third"})
    step = Step.objects.get(recipe=recipe, step_text="Third")
    assert step.index_in_sequence == 2


@pytest.mark.django_db
def test_step_create_inserts_at_posted_position(auth_client, recipe, two_steps):
    """Two drafts saved in reverse order keep their on-screen positions."""
    # Drafts were opened at DOM positions 2 and 3; the later one is saved first.
    auth_client.post(
        f"/recipes/{recipe.pk}/steps/create/", {"step_text": "Fourth", "position": "3"}
    )
    auth_client.post(f"/recipes/{recipe.pk}/steps/create/", {"step_text": "Third", "position": "2"})
    third = Step.objects.get(recipe=recipe, step_text="Third")
    fourth = Step.objects.get(recipe=recipe, step_text="Fourth")
    assert third.index_in_sequence == 2
    assert fourth.index_in_sequence == 3


@pytest.mark.django_db
def test_step_create_position_shifts_existing_rows(auth_client, recipe, two_steps):
    """Inserting before existing rows shifts them up instead of colliding."""
    first, second = two_steps
    auth_client.post(
        f"/recipes/{recipe.pk}/steps/create/", {"step_text": "Newcomer", "position": "0"}
    )
    first.refresh_from_db()
    second.refresh_from_db()
    newcomer = Step.objects.get(recipe=recipe, step_text="Newcomer")
    assert newcomer.index_in_sequence == 0
    assert first.index_in_sequence == 1
    assert second.index_in_sequence == 2


@pytest.mark.django_db
def test_step_create_position_missing_or_invalid_appends(auth_client, recipe, two_steps):
    auth_client.post(f"/recipes/{recipe.pk}/steps/create/", {"step_text": "NoPos"})
    auth_client.post(
        f"/recipes/{recipe.pk}/steps/create/", {"step_text": "BadPos", "position": "x"}
    )
    assert Step.objects.get(recipe=recipe, step_text="NoPos").index_in_sequence == 2
    assert Step.objects.get(recipe=recipe, step_text="BadPos").index_in_sequence == 3


@pytest.mark.django_db
def test_step_create_position_beyond_end_clamps_to_append(auth_client, recipe, two_steps):
    """Position counting unsaved sibling drafts clamps to the next free index."""
    auth_client.post(
        f"/recipes/{recipe.pk}/steps/create/", {"step_text": "Clamped", "position": "9"}
    )
    assert Step.objects.get(recipe=recipe, step_text="Clamped").index_in_sequence == 2


@pytest.mark.django_db
def test_step_add_form_sends_position(auth_client, recipe):
    """Draft form carries the hx-on hook that posts its DOM position on save."""
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/add/")
    content = response.content.decode()
    assert "hx-on::config-request" in content
    assert "position" in content


@pytest.mark.django_db
def test_step_create_appends_after_one_based_imported_rows(auth_client, recipe):
    """YAML importer seeds 1-based indexes; a draft saved at the visual end
    must append after the last row, not slip in front of it."""
    Step.objects.create(recipe=recipe, step_text="Imported 1", index_in_sequence=1)
    Step.objects.create(recipe=recipe, step_text="Imported 2", index_in_sequence=2)
    # Two rows on screen → draft at DOM position 2
    auth_client.post(
        f"/recipes/{recipe.pk}/steps/create/", {"step_text": "Appended", "position": "2"}
    )
    ordered = list(
        Step.objects.filter(recipe=recipe)
        .order_by("index_in_sequence")
        .values_list("step_text", flat=True)
    )
    assert ordered == ["Imported 1", "Imported 2", "Appended"]


@pytest.mark.django_db
def test_step_create_inserts_first_among_one_based_imported_rows(auth_client, recipe):
    Step.objects.create(recipe=recipe, step_text="Imported 1", index_in_sequence=1)
    Step.objects.create(recipe=recipe, step_text="Imported 2", index_in_sequence=2)
    auth_client.post(
        f"/recipes/{recipe.pk}/steps/create/", {"step_text": "Newcomer", "position": "0"}
    )
    ordered = list(
        Step.objects.filter(recipe=recipe)
        .order_by("index_in_sequence")
        .values_list("step_text", flat=True)
    )
    assert ordered == ["Newcomer", "Imported 1", "Imported 2"]


@pytest.mark.django_db
def test_step_create_invalid_creates_nothing_returns_form(auth_client, recipe):
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/create/", {"step_text": ""})
    assert response.status_code == 200
    assert Step.objects.filter(recipe=recipe).count() == 0
    assert "<form" in response.content.decode()


@pytest.mark.django_db
def test_step_add_textarea_has_placeholder(auth_client, recipe):
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/add/")
    content = response.content.decode()
    assert "placeholder=" in content
    assert "New step" in content


@pytest.mark.django_db
def test_step_add_returns_edit_partial(auth_client, recipe):
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/add/")
    content = response.content.decode()
    assert "<form" in content


@pytest.mark.django_db
def test_step_save_get_not_allowed(auth_client, recipe, step):
    response = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/save/")
    assert response.status_code == 405


@pytest.mark.django_db
def test_step_display_renders_allowed_html_tags(auth_client, recipe):
    step = Step.objects.create(
        recipe=recipe,
        step_text="<b>bold</b> and <i>italic</i> and <s>strike</s> and <u>under</u>",
        index_in_sequence=0,
    )
    response = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/")
    content = response.content.decode()
    assert "<b>bold</b>" in content
    assert "<i>italic</i>" in content
    assert "<s>strike</s>" in content
    assert "<u>under</u>" in content


@pytest.mark.django_db
def test_step_display_strips_disallowed_html_tags(auth_client, recipe):
    step = Step.objects.create(
        recipe=recipe,
        step_text="<script>evil()</script> normal text",
        index_in_sequence=0,
    )
    response = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/")
    content = response.content.decode()
    assert "<script>" not in content
    assert "evil()" in content


@pytest.mark.django_db
def test_step_display_escapes_text_outside_tags(auth_client, recipe):
    step = Step.objects.create(
        recipe=recipe,
        step_text="<b>bold</b> & normal <unknown>text</unknown>",
        index_in_sequence=0,
    )
    response = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/")
    content = response.content.decode()
    assert "<b>bold</b>" in content
    assert "&amp;" in content
    assert "<unknown>" not in content


@pytest.fixture
def three_steps(recipe):
    s0 = Step.objects.create(recipe=recipe, step_text="First", index_in_sequence=0)
    s1 = Step.objects.create(recipe=recipe, step_text="Second", index_in_sequence=1)
    s2 = Step.objects.create(recipe=recipe, step_text="Third", index_in_sequence=2)
    return s0, s1, s2


@pytest.mark.django_db
def test_step_move_up_swaps_indexes(auth_client, recipe, three_steps):
    s0, s1, _ = three_steps
    auth_client.post(f"/recipes/{recipe.pk}/steps/{s1.pk}/move-up/")
    s0.refresh_from_db()
    s1.refresh_from_db()
    assert s1.index_in_sequence == 0
    assert s0.index_in_sequence == 1


@pytest.mark.django_db
def test_step_move_down_swaps_indexes(auth_client, recipe, three_steps):
    s0, s1, _ = three_steps
    auth_client.post(f"/recipes/{recipe.pk}/steps/{s0.pk}/move-down/")
    s0.refresh_from_db()
    s1.refresh_from_db()
    assert s0.index_in_sequence == 1
    assert s1.index_in_sequence == 0


@pytest.mark.django_db
def test_step_move_up_at_first_is_noop(auth_client, recipe, three_steps):
    s0, _, _ = three_steps
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/{s0.pk}/move-up/")
    assert response.status_code == 200
    s0.refresh_from_db()
    assert s0.index_in_sequence == 0


@pytest.mark.django_db
def test_step_move_down_at_last_is_noop(auth_client, recipe, three_steps):
    _, _, s2 = three_steps
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/{s2.pk}/move-down/")
    assert response.status_code == 200
    s2.refresh_from_db()
    assert s2.index_in_sequence == 2


@pytest.mark.django_db
def test_step_move_returns_steps_list(auth_client, recipe, three_steps):
    _, s1, _ = three_steps
    response = auth_client.post(f"/recipes/{recipe.pk}/steps/{s1.pk}/move-up/")
    content = response.content.decode()
    assert "First" in content
    assert "Second" in content
    assert "Third" in content


@pytest.mark.django_db
def test_step_edit_partial_has_is_editing_class(auth_client, recipe):
    """Edit template must render is-editing class so CSS can block move buttons."""
    step = Step.objects.create(recipe=recipe, step_text="Edit me", index_in_sequence=0)
    response = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/edit/")
    assert "is-editing" in response.content.decode()


@pytest.mark.django_db
def test_step_create_recipe_deleted_concurrently_returns_404(auth_client, recipe):
    """step_create must abort with 404 if recipe is deleted after get_object_or_404."""
    from unittest.mock import patch

    from django.db.models import QuerySet

    original_sfu = QuerySet.select_for_update
    deleted = []

    def delete_recipe_at_lock(qs, *args, **kwargs):
        if qs.model is Recipe and not deleted:
            deleted.append(True)
            Recipe.objects.filter(pk=recipe.pk).delete()
        return original_sfu(qs, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", delete_recipe_at_lock):
        response = auth_client.post(
            f"/recipes/{recipe.pk}/steps/create/",
            {"step_text": "Simmer for 30 minutes"},
        )

    assert response.status_code == 404
    assert not Step.objects.filter(step_text="Simmer for 30 minutes").exists()


@pytest.mark.django_db
def test_step_save_step_deleted_concurrently_returns_404(auth_client, recipe, step):
    """recipe_step_save must return 404 if step is deleted after get_object_or_404."""
    from unittest.mock import patch

    from django.db.models import QuerySet

    original_sfu = QuerySet.select_for_update
    deleted = []

    def delete_step_at_lock(qs, *args, **kwargs):
        if qs.model is Step and not deleted:
            deleted.append(True)
            Step.objects.filter(pk=step.pk).delete()
        return original_sfu(qs, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", delete_step_at_lock):
        response = auth_client.post(
            f"/recipes/{recipe.pk}/steps/{step.pk}/save/",
            {"step_text": "Updated text"},
        )

    assert response.status_code == 404
    assert not Step.objects.filter(pk=step.pk).exists()


@pytest.mark.django_db
def test_step_save_preserves_concurrent_index_change(auth_client, recipe, step):
    """recipe_step_save must not undo a concurrent reorder by writing stale index_in_sequence."""
    from unittest.mock import patch

    from django.db.models import QuerySet

    original_sfu = QuerySet.select_for_update
    moved = []

    def reorder_at_lock(qs, *args, **kwargs):
        if qs.model is Step and not moved:
            moved.append(True)
            Step.objects.filter(pk=step.pk).update(index_in_sequence=5)
        return original_sfu(qs, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", reorder_at_lock):
        response = auth_client.post(
            f"/recipes/{recipe.pk}/steps/{step.pk}/save/",
            {"step_text": "Updated text"},
        )

    assert response.status_code == 200
    step.refresh_from_db()
    assert step.index_in_sequence == 5  # concurrent reorder preserved
    assert step.step_text == "Updated text"  # form edit applied


@pytest.mark.django_db
def test_step_display_shows_title(auth_client, recipe):
    step = Step.objects.create(
        recipe=recipe, step_text="Warm the milk", step_title="BECHAMEL", index_in_sequence=0
    )
    content = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/").content.decode()
    assert "BECHAMEL" in content
    assert "step-title" in content


@pytest.mark.django_db
def test_step_display_omits_title_element_when_blank(auth_client, recipe, step):
    content = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/").content.decode()
    assert "step-title" not in content


@pytest.mark.django_db
def test_step_display_escapes_html_in_title(auth_client, recipe):
    """A title carries no markup — unlike step_text, it is escaped outright."""
    step = Step.objects.create(
        recipe=recipe, step_text="Warm the milk", step_title="<b>BOLD</b>", index_in_sequence=0
    )
    content = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/").content.decode()
    assert "<b>BOLD</b>" not in content
    assert "&lt;b&gt;BOLD&lt;/b&gt;" in content


@pytest.mark.django_db
def test_step_edit_form_has_title_input_with_value(auth_client, recipe):
    step = Step.objects.create(
        recipe=recipe, step_text="Warm the milk", step_title="BECHAMEL", index_in_sequence=0
    )
    content = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/edit/").content.decode()
    assert 'name="step_title"' in content
    assert 'value="BECHAMEL"' in content


@pytest.mark.django_db
def test_step_add_title_input_has_placeholder(auth_client, recipe):
    content = auth_client.post(f"/recipes/{recipe.pk}/steps/add/").content.decode()
    assert 'name="step_title"' in content
    assert "Title (optional)" in content


@pytest.mark.django_db
def test_step_save_persists_title(auth_client, recipe, step):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/{step.pk}/save/",
        {"step_title": "BECHAMEL", "step_text": "Warm the milk"},
    )
    assert response.status_code == 200
    step.refresh_from_db()
    assert step.step_title == "BECHAMEL"
    assert step.step_text == "Warm the milk"


@pytest.mark.django_db
def test_step_save_can_clear_title(auth_client, recipe):
    step = Step.objects.create(
        recipe=recipe, step_text="Warm the milk", step_title="BECHAMEL", index_in_sequence=0
    )
    auth_client.post(
        f"/recipes/{recipe.pk}/steps/{step.pk}/save/",
        {"step_title": "", "step_text": "Warm the milk"},
    )
    step.refresh_from_db()
    assert step.step_title == ""


@pytest.mark.django_db
def test_step_save_without_a_title_still_saves(auth_client, recipe, step):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/steps/{step.pk}/save/", {"step_text": "Chop the onions"}
    )
    assert response.status_code == 200
    step.refresh_from_db()
    assert step.step_text == "Chop the onions"
    assert step.step_title == ""


@pytest.mark.django_db
def test_step_create_accepts_a_title(auth_client, recipe):
    auth_client.post(
        f"/recipes/{recipe.pk}/steps/create/",
        {"step_title": "RAGÚ", "step_text": "Brown the beef"},
    )
    created = Step.objects.get(recipe=recipe, step_text="Brown the beef")
    assert created.step_title == "RAGÚ"


@pytest.mark.django_db
def test_step_display_writes_a_colon_after_the_title(auth_client, recipe):
    """The colon is punctuation between title and text, so it sits outside the span."""
    step = Step.objects.create(
        recipe=recipe, step_text="Warm the milk", step_title="Bechamel", index_in_sequence=0
    )
    content = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/").content.decode()
    assert '<span class="step-title">Bechamel</span>:' in content


@pytest.mark.django_db
def test_step_display_writes_no_colon_without_a_title(auth_client, recipe, step):
    content = auth_client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/").content.decode()
    assert "</span>:" not in content
