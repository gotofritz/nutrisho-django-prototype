"""Tests for recipe field inline-edit views (Plan 004, Step 2)."""

import pytest
from django.test import Client

from recipes.models import Recipe


@pytest.fixture
def auth_client(user):
    """Auth client."""
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def recipe(user, db):
    """Recipe."""
    return Recipe.objects.create(recipe_name="Editable Recipe", owner=user, servings=2)


@pytest.mark.django_db
def test_field_display_get_returns_200(auth_client, recipe):
    """Field display get returns 200."""
    response = auth_client.get(f"/recipes/{recipe.pk}/field/recipe_name/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_field_display_no_form_elements(auth_client, recipe):
    """Field display no form elements."""
    response = auth_client.get(f"/recipes/{recipe.pk}/field/recipe_name/")
    content = response.content.decode()
    assert "<form" not in content
    assert "<input" not in content


@pytest.mark.django_db
def test_field_display_shows_current_value(auth_client, recipe):
    """Field display shows current value."""
    response = auth_client.get(f"/recipes/{recipe.pk}/field/recipe_name/")
    assert recipe.recipe_name.encode() in response.content


@pytest.mark.django_db
def test_field_display_unknown_field_returns_404(auth_client, recipe):
    """Field display unknown field returns 404."""
    response = auth_client.get(f"/recipes/{recipe.pk}/field/unknown_field/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_field_display_nonexistent_recipe_returns_404(auth_client, db):
    """Field display nonexistent recipe returns 404."""
    response = auth_client.get("/recipes/99999/field/recipe_name/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_field_edit_get_returns_200(auth_client, recipe):
    """Field edit get returns 200."""
    response = auth_client.get(f"/recipes/{recipe.pk}/field/recipe_name/edit/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_field_edit_returns_form_with_current_value(auth_client, recipe):
    """Field edit returns form with current value."""
    response = auth_client.get(f"/recipes/{recipe.pk}/field/recipe_name/edit/")
    content = response.content.decode()
    assert "<form" in content
    assert recipe.recipe_name in content


@pytest.mark.django_db
def test_field_edit_cancel_button_points_to_display(auth_client, recipe):
    """Field edit cancel button points to display."""
    response = auth_client.get(f"/recipes/{recipe.pk}/field/recipe_name/edit/")
    content = response.content.decode()
    display_url = f"/recipes/{recipe.pk}/field/recipe_name/"
    assert display_url in content


@pytest.mark.django_db
def test_field_edit_unknown_field_returns_404(auth_client, recipe):
    """Field edit unknown field returns 404."""
    response = auth_client.get(f"/recipes/{recipe.pk}/field/unknown_field/edit/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_field_save_post_valid_saves_and_returns_display(auth_client, recipe):
    """Field save post valid saves and returns display."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/field/recipe_name/save/",
        {"recipe_name": "Updated Name"},
    )
    assert response.status_code == 200
    recipe.refresh_from_db()
    assert recipe.recipe_name == "Updated Name"
    content = response.content.decode()
    assert "<form" not in content


@pytest.mark.django_db
def test_field_save_accepts_a_description_longer_than_512(auth_client, recipe):
    """Imported blurbs exceed 512 characters; the inline editor must save them (#49)."""
    long_text = "a" * 600
    response = auth_client.post(
        f"/recipes/{recipe.pk}/field/short_description/save/",
        {"short_description": long_text},
    )
    assert "<form" not in response.content.decode()
    recipe.refresh_from_db()
    assert recipe.short_description == long_text


@pytest.mark.django_db
def test_field_save_post_invalid_returns_form_with_errors(auth_client, recipe):
    """Field save post invalid returns form with errors."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/field/recipe_name/save/",
        {"recipe_name": ""},  # required field
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "<form" in content


@pytest.mark.django_db
def test_field_save_blank_servings_returns_form_with_errors(auth_client, recipe):
    """Servings is mandatory: clearing it inline re-renders the edit form, value unchanged."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/field/servings/save/",
        {"servings": ""},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "<form" in content
    recipe.refresh_from_db()
    assert recipe.servings == 2


@pytest.mark.django_db
def test_field_save_nonexistent_recipe_returns_404(auth_client, db):
    """Field save nonexistent recipe returns 404."""
    response = auth_client.post("/recipes/99999/field/recipe_name/save/", {"recipe_name": "x"})
    assert response.status_code == 404


@pytest.mark.django_db
def test_field_save_get_not_allowed(auth_client, recipe):
    """Field save get not allowed."""
    response = auth_client.get(f"/recipes/{recipe.pk}/field/recipe_name/save/")
    assert response.status_code == 405


@pytest.mark.django_db
def test_field_save_integrity_error_returns_edit_form_with_error(auth_client, recipe):
    """Concurrent rename race: IntegrityError from form.save() must return edit partial with error."""
    from unittest.mock import patch

    from django.db import IntegrityError

    with patch("recipes.views.recipe_fields.RecipeFieldForm.save", side_effect=IntegrityError):
        response = auth_client.post(
            f"/recipes/{recipe.pk}/field/recipe_name/save/",
            {"recipe_name": recipe.recipe_name},
        )
    assert response.status_code == 200
    content = response.content.decode()
    assert "<form" in content
    assert "already have" in content


@pytest.mark.django_db
def test_field_save_recipe_deleted_concurrently_returns_404(auth_client, recipe):
    """recipe_field_save must return 404 if recipe is deleted after get_object_or_404."""
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
            f"/recipes/{recipe.pk}/field/short_description/save/",
            {"short_description": "Updated"},
        )

    assert response.status_code == 404
    assert not Recipe.objects.filter(pk=recipe.pk).exists()


@pytest.mark.django_db
def test_field_save_preserves_concurrent_other_field_change(auth_client, recipe):
    """recipe_field_save(servings) must not overwrite a concurrently edited short_description."""
    from unittest.mock import patch

    from django.db.models import QuerySet

    recipe.short_description = "Original"
    recipe.save(update_fields=["short_description"])

    original_sfu = QuerySet.select_for_update
    edited = []

    def update_desc_at_lock(qs, *args, **kwargs):
        if qs.model is Recipe and not edited:
            edited.append(True)
            Recipe.objects.filter(pk=recipe.pk).update(short_description="Concurrent edit")
        return original_sfu(qs, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", update_desc_at_lock):
        response = auth_client.post(
            f"/recipes/{recipe.pk}/field/servings/save/",
            {"servings": "8"},
        )

    assert response.status_code == 200
    recipe.refresh_from_db()
    assert recipe.servings == 8
    assert recipe.short_description == "Concurrent edit"  # not overwritten


@pytest.mark.django_db
def test_field_display_renders_title_formatting(auth_client, recipe):
    """Underline and strikethrough in the title render as markup."""
    recipe.recipe_name = "<u>Ragú</u> <s>old</s> <script>x()</script>"
    recipe.save()
    content = auth_client.get(f"/recipes/{recipe.pk}/field/recipe_name/").content.decode()
    assert "<u>Ragú</u> <s>old</s> x()</span>" in content
    assert "<script>" not in content


@pytest.mark.django_db
def test_field_display_renders_blurb_formatting(auth_client, recipe):
    """Basic formatting and new lines in the blurb render as markup."""
    recipe.short_description = "<b>Rich</b> and <i>quick</i>\n<script>x()</script>"
    recipe.save()
    content = auth_client.get(f"/recipes/{recipe.pk}/field/short_description/").content.decode()
    assert "<b>Rich</b> and <i>quick</i><br>x()</span>" in content
    assert "<script>" not in content


@pytest.mark.django_db
def test_field_display_empty_blurb_shows_placeholder(auth_client, recipe):
    """An empty blurb still shows the dash placeholder."""
    content = auth_client.get(f"/recipes/{recipe.pk}/field/short_description/").content.decode()
    assert "data-empty" in content
    assert ">—</span>" in content


@pytest.mark.django_db
def test_field_display_servings_unchanged(auth_client, recipe):
    """Servings render as plain text, as before."""
    content = auth_client.get(f"/recipes/{recipe.pk}/field/servings/").content.decode()
    assert ">2</span>" in content


@pytest.mark.django_db
def test_recipe_page_title_element_strips_tags(auth_client, recipe):
    """The browser tab cannot render markup, so the <title> element gets plain text."""
    recipe.recipe_name = "<u>Ragú</u> & co"
    recipe.save()
    content = auth_client.get(recipe.get_absolute_url()).content.decode()
    assert "<title>Ragú &amp; co</title>" in content


@pytest.mark.django_db
def test_recipe_list_renders_title_formatting(auth_client, recipe):
    """The recipe list renders the title's markup and keeps the delete prompt plain."""
    recipe.recipe_name = "<s>Old</s> Ragú"
    recipe.save()
    content = auth_client.get("/recipes/").content.decode()
    assert 'class="recipe-name"><s>Old</s> Ragú</a>' in content
    assert "hx-confirm=\"Delete 'Old Ragú'?\"" in content
