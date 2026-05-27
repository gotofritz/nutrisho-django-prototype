"""Tests for recipe step inline-edit views (Plan 004, Step 2)."""

import pytest
from django.test import Client

from recipes.models import Recipe, Step


@pytest.fixture
def client():
    return Client()


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
def test_step_display_get_returns_200(client, recipe, step):
    response = client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_step_display_no_form_elements(client, recipe, step):
    response = client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/")
    content = response.content.decode()
    assert "<form" not in content


@pytest.mark.django_db
def test_step_display_shows_step_text(client, recipe, step):
    response = client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/")
    assert step.step_text.encode() in response.content


@pytest.mark.django_db
def test_step_display_404_wrong_recipe(client, user, db):
    other = Recipe.objects.create(recipe_name="Other", owner=user)
    step = Step.objects.create(recipe=other, step_text="x", index_in_sequence=0)
    recipe = Recipe.objects.create(recipe_name="Mine", owner=user)
    response = client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_step_edit_get_returns_200(client, recipe, step):
    response = client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/edit/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_step_edit_has_form_with_value(client, recipe, step):
    response = client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/edit/")
    content = response.content.decode()
    assert "<form" in content
    assert step.step_text in content


@pytest.mark.django_db
def test_step_edit_cancel_button_points_to_display(client, recipe, step):
    response = client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/edit/")
    content = response.content.decode()
    display_url = f"/recipes/{recipe.pk}/steps/{step.pk}/"
    assert display_url in content


@pytest.mark.django_db
def test_step_save_post_valid_saves_and_returns_display(client, recipe, step):
    response = client.post(
        f"/recipes/{recipe.pk}/steps/{step.pk}/save/",
        {"step_text": "Updated step text"},
    )
    assert response.status_code == 200
    step.refresh_from_db()
    assert step.step_text == "Updated step text"
    content = response.content.decode()
    assert "<form" not in content


@pytest.mark.django_db
def test_step_save_post_invalid_returns_form(client, recipe, step):
    response = client.post(
        f"/recipes/{recipe.pk}/steps/{step.pk}/save/",
        {"step_text": ""},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "<form" in content


@pytest.mark.django_db
def test_step_delete_removes_step(client, recipe, step):
    step_id = step.pk
    response = client.post(f"/recipes/{recipe.pk}/steps/{step_id}/delete/")
    assert response.status_code == 200
    assert not Step.objects.filter(pk=step_id).exists()


@pytest.mark.django_db
def test_step_delete_reorders_remaining(client, recipe, two_steps):
    first, second = two_steps
    client.post(f"/recipes/{recipe.pk}/steps/{first.pk}/delete/")
    second.refresh_from_db()
    assert second.index_in_sequence == 0


@pytest.mark.django_db
def test_step_add_creates_step(client, recipe):
    response = client.post(f"/recipes/{recipe.pk}/steps/add/")
    assert response.status_code == 200
    assert Step.objects.filter(recipe=recipe).count() == 1


@pytest.mark.django_db
def test_step_add_returns_edit_partial(client, recipe):
    response = client.post(f"/recipes/{recipe.pk}/steps/add/")
    content = response.content.decode()
    assert "<form" in content


@pytest.mark.django_db
def test_step_save_get_not_allowed(client, recipe, step):
    response = client.get(f"/recipes/{recipe.pk}/steps/{step.pk}/save/")
    assert response.status_code == 405
