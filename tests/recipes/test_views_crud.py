"""Tests for recipe create/delete/metadata views."""

import pytest
from django.test import Client

from recipes.models import Cuisine, Recipe, Source


@pytest.fixture
def auth_client(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def recipe(user, db):
    return Recipe.objects.create(recipe_name="Delete Me", owner=user)


@pytest.fixture
def cuisine(db):
    return Cuisine.objects.create(cuisine="Italian")


@pytest.fixture
def source(db):
    return Source.objects.create(short_name="Moro", source="ISBN 9781856267991")


# --- Create ---


@pytest.mark.django_db
def test_recipe_new_get_returns_200(auth_client):
    response = auth_client.get("/recipes/new/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_recipe_new_get_has_form(auth_client):
    response = auth_client.get("/recipes/new/")
    assert "form" in response.context


@pytest.mark.django_db
def test_recipe_new_form_has_text_fields(auth_client):
    response = auth_client.get("/recipes/new/")
    form = response.context["form"]
    for field in (
        "recipe_name",
        "short_description",
        "servings",
        "cuisine_name",
        "source_instance",
    ):
        assert field in form.fields, f"missing field: {field}"


@pytest.mark.django_db
def test_recipe_new_form_has_no_source_fk(auth_client):
    response = auth_client.get("/recipes/new/")
    assert "source" not in response.context["form"].fields


@pytest.mark.django_db
def test_recipe_new_form_cuisine_is_charfield(auth_client):
    from django.forms import CharField

    response = auth_client.get("/recipes/new/")
    assert isinstance(response.context["form"].fields["cuisine_name"], CharField)


@pytest.mark.django_db
def test_recipe_new_post_valid_creates_recipe_and_redirects(auth_client, user):
    response = auth_client.post("/recipes/new/", {"recipe_name": "Brand New Recipe"})
    assert response.status_code == 302
    assert Recipe.objects.filter(recipe_name="Brand New Recipe").exists()


@pytest.mark.django_db
def test_recipe_new_post_saves_metadata(auth_client, user):
    response = auth_client.post(
        "/recipes/new/",
        {
            "recipe_name": "Meta Recipe",
            "short_description": "A test",
            "servings": "4",
            "cuisine_name": "Italian",
            "source_instance": "p.42",
        },
    )
    assert response.status_code == 302
    recipe = Recipe.objects.get(recipe_name="Meta Recipe")
    assert recipe.short_description == "A test"
    assert recipe.servings == 4
    assert recipe.cuisine is not None
    assert recipe.cuisine.cuisine == "Italian"
    assert recipe.source_instance == "p.42"


@pytest.mark.django_db
def test_recipe_new_post_creates_cuisine_if_new(auth_client, user):
    assert not Cuisine.objects.filter(cuisine="Peruvian").exists()
    auth_client.post("/recipes/new/", {"recipe_name": "Ceviche", "cuisine_name": "Peruvian"})
    assert Cuisine.objects.filter(cuisine="Peruvian").exists()


@pytest.mark.django_db
def test_recipe_new_post_reuses_existing_cuisine(auth_client, user, cuisine):
    auth_client.post("/recipes/new/", {"recipe_name": "Pasta", "cuisine_name": "Italian"})
    assert Cuisine.objects.filter(cuisine="Italian").count() == 1


@pytest.mark.django_db
def test_recipe_new_post_invalid_returns_200_with_errors(auth_client, user):
    response = auth_client.post("/recipes/new/", {"recipe_name": ""})
    assert response.status_code == 200
    assert "form" in response.context
    assert response.context["form"].errors


@pytest.mark.django_db
def test_recipe_new_post_duplicate_name_returns_error(auth_client, recipe):
    response = auth_client.post("/recipes/new/", {"recipe_name": recipe.recipe_name})
    assert response.status_code == 200
    assert "form" in response.context


@pytest.mark.django_db
def test_recipe_new_post_integrity_error_returns_form_error(auth_client, user):
    """Concurrent create race: IntegrityError from recipe.save() must be caught and shown as a form error."""
    from unittest.mock import patch

    from django.db import IntegrityError

    with patch("recipes.models.Recipe.save", side_effect=IntegrityError):
        response = auth_client.post("/recipes/new/", {"recipe_name": "Race Condition Recipe"})
    assert response.status_code == 200
    assert "form" in response.context
    assert response.context["form"].errors


@pytest.mark.django_db
def test_recipe_metadata_post_integrity_error_returns_form_error(auth_client, recipe):
    """Concurrent rename race: IntegrityError from form.save() must be caught and shown as a form error."""
    from unittest.mock import patch

    from django.db import IntegrityError

    with patch("recipes.views.recipe_crud.RecipeMetadataForm.save", side_effect=IntegrityError):
        response = auth_client.post(
            f"/recipes/{recipe.pk}/metadata/",
            {"recipe_name": recipe.recipe_name},
        )
    assert response.status_code == 200
    assert "form" in response.context
    assert response.context["form"].errors


@pytest.mark.django_db
def test_recipe_new_htmx_post_valid_returns_hx_redirect(auth_client, user):
    """Boosted form submit must get HX-Redirect, not a plain 302."""
    response = auth_client.post(
        "/recipes/new/",
        {"recipe_name": "HTMX New Recipe"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert "HX-Redirect" in response
    recipe = Recipe.objects.get(recipe_name="HTMX New Recipe")
    assert response["HX-Redirect"] == recipe.get_absolute_url()


# --- Metadata edit ---


@pytest.mark.django_db
def test_recipe_metadata_get_returns_200(auth_client, recipe):
    response = auth_client.get(f"/recipes/{recipe.pk}/metadata/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_recipe_metadata_get_has_form(auth_client, recipe):
    response = auth_client.get(f"/recipes/{recipe.pk}/metadata/")
    assert "form" in response.context


@pytest.mark.django_db
def test_recipe_metadata_post_saves_and_redirects(auth_client, recipe):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/metadata/",
        {"recipe_name": recipe.recipe_name, "cuisine_name": "French", "source_instance": "p.10"},
    )
    assert response.status_code == 302
    recipe.refresh_from_db()
    assert recipe.source_instance == "p.10"
    assert recipe.cuisine.cuisine == "French"


@pytest.mark.django_db
def test_recipe_metadata_post_invalid_returns_form(auth_client, recipe):
    response = auth_client.post(f"/recipes/{recipe.pk}/metadata/", {"recipe_name": ""})
    assert response.status_code == 200
    assert response.context["form"].errors


# --- Metadata edit (HTMX) ---


@pytest.mark.django_db
def test_recipe_metadata_htmx_get_returns_partial(auth_client, recipe):
    response = auth_client.get(
        f"/recipes/{recipe.pk}/metadata/",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert "recipes/partials/_metadata_panel.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_recipe_metadata_htmx_post_valid_returns_hx_redirect(auth_client, recipe):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/metadata/",
        {"recipe_name": recipe.recipe_name, "cuisine_name": "Spanish"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert "HX-Redirect" in response


@pytest.mark.django_db
def test_recipe_metadata_htmx_post_invalid_returns_partial(auth_client, recipe):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/metadata/",
        {"recipe_name": ""},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert "recipes/partials/_metadata_panel.html" in [t.name for t in response.templates]
    assert response.context["form"].errors


@pytest.mark.django_db
def test_recipe_metadata_boosted_get_returns_full_page(auth_client, recipe):
    """hx-boost on <body> boosts the list page's Edit metadata link; boosted
    navigation must get the full page, not the inline panel fragment."""
    response = auth_client.get(
        f"/recipes/{recipe.pk}/metadata/",
        HTTP_HX_REQUEST="true",
        HTTP_HX_BOOSTED="true",
    )
    assert response.status_code == 200
    assert "recipes/recipe_metadata.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_recipe_metadata_boosted_post_invalid_returns_full_page(auth_client, recipe):
    response = auth_client.post(
        f"/recipes/{recipe.pk}/metadata/",
        {"recipe_name": ""},
        HTTP_HX_REQUEST="true",
        HTTP_HX_BOOSTED="true",
    )
    assert response.status_code == 200
    assert "recipes/recipe_metadata.html" in [t.name for t in response.templates]
    assert response.context["form"].errors


# --- List page ---


@pytest.mark.django_db
def test_recipe_list_has_edit_metadata_button(auth_client, recipe):
    response = auth_client.get("/recipes/")
    content = response.content.decode()
    assert f"/recipes/{recipe.pk}/metadata/" in content


@pytest.mark.django_db
def test_recipe_list_has_view_button(auth_client, recipe):
    response = auth_client.get("/recipes/")
    content = response.content.decode()
    assert f'href="{recipe.get_absolute_url()}"' in content


# --- Delete confirm panel ---


@pytest.mark.django_db
def test_recipe_delete_panel_get_returns_partial(auth_client, recipe):
    response = auth_client.get(
        f"/recipes/{recipe.pk}/delete/panel/",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert "recipes/partials/_delete_confirm_panel.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_recipe_delete_panel_has_delete_url(auth_client, recipe):
    response = auth_client.get(
        f"/recipes/{recipe.pk}/delete/panel/",
        HTTP_HX_REQUEST="true",
    )
    assert f"/recipes/{recipe.pk}/delete/" in response.content.decode()


# --- Delete ---


@pytest.mark.django_db
def test_recipe_delete_removes_recipe(auth_client, recipe):
    recipe_id = recipe.pk
    response = auth_client.post(f"/recipes/{recipe_id}/delete/", HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert not Recipe.objects.filter(pk=recipe_id).exists()


@pytest.mark.django_db
def test_recipe_delete_htmx_returns_hx_redirect(auth_client, recipe):
    """Detail-page HTMX delete returns HX-Redirect so HTMX navigates client-side."""
    response = auth_client.post(f"/recipes/{recipe.pk}/delete/", HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert "HX-Redirect" in response
    assert response.content == b""


@pytest.mark.django_db
def test_recipe_delete_last_from_list_returns_empty_state(auth_client, recipe):
    """Deleting the final recipe from the list page swaps in the empty state."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/delete/",
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET=f"recipe-{recipe.pk}",
    )
    assert response.status_code == 200
    assert "No recipes are available." in response.content.decode()
    assert response["HX-Retarget"] == "#recipe-list"
    assert response["HX-Reswap"] == "outerHTML"


@pytest.mark.django_db
def test_recipe_delete_from_list_with_remaining_returns_empty_body(auth_client, user, recipe):
    """Row delete with other recipes left still returns empty 200 (row removal only)."""
    Recipe.objects.create(recipe_name="Still Here", owner=user)
    response = auth_client.post(
        f"/recipes/{recipe.pk}/delete/",
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET=f"recipe-{recipe.pk}",
    )
    assert response.status_code == 200
    assert response.content == b""
    assert "HX-Retarget" not in response


@pytest.mark.django_db
def test_recipe_delete_last_from_detail_panel_redirects_to_list(auth_client, recipe):
    """Detail-page delete with no remaining recipes redirects to the list page."""
    response = auth_client.post(f"/recipes/{recipe.pk}/delete/", HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert response["HX-Redirect"] == "/recipes/"
    assert "HX-Retarget" not in response


@pytest.mark.django_db
def test_recipe_delete_hx_redirect_points_to_next_recipe(auth_client, user, recipe, db):
    """Detail delete POST sets HX-Redirect to the next recipe's URL."""
    other = Recipe.objects.create(recipe_name="Other", owner=user)
    response = auth_client.post(
        f"/recipes/{recipe.pk}/delete/",
        HTTP_HX_REQUEST="true",
    )
    assert response["HX-Redirect"] == other.get_absolute_url()


@pytest.mark.django_db
def test_recipe_delete_hx_redirect_falls_back_to_list(auth_client, recipe):
    """Detail delete POST redirects to /recipes/ when no other recipes exist."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/delete/",
        HTTP_HX_REQUEST="true",
    )
    assert response["HX-Redirect"] == "/recipes/"


@pytest.mark.django_db
def test_recipe_delete_hx_redirect_prefers_next_over_prev(auth_client, user, db):
    """HX-Redirect after delete prefers higher-id neighbor over lower-id."""
    owner = user
    Recipe.objects.create(recipe_name="Prev", owner=owner)
    mid = Recipe.objects.create(recipe_name="Mid", owner=owner)
    nxt = Recipe.objects.create(recipe_name="Next", owner=owner)
    response = auth_client.post(
        f"/recipes/{mid.pk}/delete/",
        HTTP_HX_REQUEST="true",
    )
    assert response["HX-Redirect"] == nxt.get_absolute_url()


@pytest.mark.django_db
def test_recipe_delete_non_htmx_redirects_to_list(auth_client, recipe):
    """Non-HTMX delete (e.g. plain form submit) redirects back to list."""
    response = auth_client.post(f"/recipes/{recipe.pk}/delete/")
    assert response.status_code == 302
    assert response["Location"] == "/recipes/"


@pytest.mark.django_db
def test_recipe_delete_404_on_missing(auth_client, db):
    response = auth_client.post("/recipes/99999/delete/", HTTP_HX_REQUEST="true")
    assert response.status_code == 404


@pytest.mark.django_db
def test_recipe_delete_get_not_allowed(auth_client, recipe):
    response = auth_client.get(f"/recipes/{recipe.pk}/delete/")
    assert response.status_code == 405


@pytest.mark.django_db
def test_recipe_new_short_description_is_textarea(auth_client):
    response = auth_client.get("/recipes/new/")
    content = response.content.decode()
    assert "<textarea" in content
    assert 'name="short_description"' in content


@pytest.mark.django_db
def test_recipe_metadata_short_description_is_textarea(auth_client, recipe):
    response = auth_client.get(f"/recipes/{recipe.pk}/metadata/")
    content = response.content.decode()
    assert "<textarea" in content
    assert 'name="short_description"' in content


@pytest.mark.django_db
def test_recipe_metadata_vary_header_present(auth_client, recipe):
    """Vary: HX-Request, HX-Boosted must be set so caches key on both headers."""
    response = auth_client.get(f"/recipes/{recipe.pk}/metadata/")
    vary = response.get("Vary", "")
    assert "HX-Request" in vary
    assert "HX-Boosted" in vary


@pytest.mark.django_db
def test_recipe_new_integrity_error_does_not_leave_orphan_cuisine(auth_client, user):
    """When recipe.save() races and raises IntegrityError, no orphan Cuisine row must be left."""
    from unittest.mock import patch

    from django.db import IntegrityError

    assert not Cuisine.objects.filter(cuisine="Orphan Cuisine").exists()
    with patch("recipes.models.Recipe.save", side_effect=IntegrityError):
        auth_client.post("/recipes/new/", {"recipe_name": "Race", "cuisine_name": "Orphan Cuisine"})
    assert not Cuisine.objects.filter(cuisine="Orphan Cuisine").exists()


@pytest.mark.django_db
def test_recipe_metadata_integrity_error_does_not_leave_orphan_cuisine(auth_client, recipe):
    """When metadata form.save() races and raises IntegrityError, no orphan Cuisine row left."""
    from unittest.mock import patch

    from django.db import IntegrityError

    assert not Cuisine.objects.filter(cuisine="Orphan Cuisine 2").exists()
    with patch("recipes.models.Recipe.save", side_effect=IntegrityError):
        auth_client.post(
            f"/recipes/{recipe.pk}/metadata/",
            {"recipe_name": recipe.recipe_name, "cuisine_name": "Orphan Cuisine 2"},
        )
    assert not Cuisine.objects.filter(cuisine="Orphan Cuisine 2").exists()


# --- Owner-scoped uniqueness ---


@pytest.mark.django_db
def test_two_owners_can_share_recipe_name(db):
    """Different owners must be able to create a recipe with the same name."""
    from django.contrib.auth.models import User

    alice = User.objects.create_user(username="alice", password="x")
    bob = User.objects.create_user(username="bob", password="x")
    Recipe.objects.create(recipe_name="Soup", owner=alice)
    # Must not raise IntegrityError
    Recipe.objects.create(recipe_name="Soup", owner=bob)
    assert Recipe.objects.filter(recipe_name="Soup").count() == 2


@pytest.mark.django_db
def test_same_owner_cannot_duplicate_recipe_name(user, db):
    """Same owner cannot have two recipes with identical names."""
    from django.db import IntegrityError

    Recipe.objects.create(recipe_name="Soup", owner=user)
    with pytest.raises(IntegrityError):
        Recipe.objects.create(recipe_name="Soup", owner=user)


@pytest.mark.django_db
def test_recipe_new_post_duplicate_name_for_same_owner_returns_error(auth_client, recipe):
    """POST /recipes/new/ with a name the same owner already has → 200 with form error."""
    response = auth_client.post("/recipes/new/", {"recipe_name": recipe.recipe_name})
    assert response.status_code == 200
    assert response.context["form"].errors


@pytest.mark.django_db
def test_recipe_new_post_duplicate_name_other_owner_succeeds(db):
    """POST /recipes/new/ with a name used by another owner must succeed."""
    from django.contrib.auth.models import User

    alice = User.objects.create_user(username="alice2", password="x")
    bob = User.objects.create_user(username="bob2", password="x")
    Recipe.objects.create(recipe_name="Chowder", owner=alice)

    c = Client()
    c.force_login(bob)
    response = c.post("/recipes/new/", {"recipe_name": "Chowder"})
    assert response.status_code == 302
    assert Recipe.objects.filter(recipe_name="Chowder", owner=bob).exists()


@pytest.mark.django_db
def test_metadata_save_recipe_deleted_concurrently_returns_404(auth_client, recipe):
    """recipe_metadata_edit must return 404 if recipe is deleted after get_object_or_404."""
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
            f"/recipes/{recipe.pk}/metadata/",
            {"recipe_name": "New Name"},
        )

    assert response.status_code == 404
    assert not Recipe.objects.filter(pk=recipe.pk).exists()


@pytest.mark.django_db
def test_metadata_save_preserves_field_not_in_form(auth_client, recipe, source):
    """recipe_metadata_edit must not overwrite fields outside the form (e.g. source FK)."""
    from unittest.mock import patch

    from django.db.models import QuerySet

    recipe.source = source
    recipe.save(update_fields=["source"])

    original_sfu = QuerySet.select_for_update
    edited = []

    def set_yaml_at_lock(qs, *args, **kwargs):
        if qs.model is Recipe and not edited:
            edited.append(True)
            Recipe.objects.filter(pk=recipe.pk).update(yaml_filename="imported.yaml")
        return original_sfu(qs, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", set_yaml_at_lock):
        response = auth_client.post(
            f"/recipes/{recipe.pk}/metadata/",
            {"recipe_name": recipe.recipe_name, "short_description": "Updated", "servings": ""},
            HTTP_HX_REQUEST="true",
        )

    assert response.status_code == 200  # HX-Redirect
    recipe.refresh_from_db()
    assert recipe.short_description == "Updated"
    assert recipe.yaml_filename == "imported.yaml"  # not overwritten


@pytest.mark.django_db
def test_recipe_delete_from_detail_returns_hx_redirect(auth_client, recipe):
    """Detail-page delete must return HX-Redirect so HTMX navigates; no client-side JS needed."""
    response = auth_client.post(
        f"/recipes/{recipe.pk}/delete/",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert "HX-Redirect" in response


@pytest.mark.django_db
def test_recipe_delete_redirects_to_fresh_next_recipe(auth_client, user, db):
    """HX-Redirect must reflect the neighbor set at delete time, not at panel-render time."""
    r1 = Recipe.objects.create(recipe_name="R1", owner=user)
    r2 = Recipe.objects.create(recipe_name="R2", owner=user)
    r3 = Recipe.objects.create(recipe_name="R3", owner=user)
    # Panel was opened while r3 existed, but r3 gets deleted before confirm
    r3.delete()
    response = auth_client.post(
        f"/recipes/{r2.pk}/delete/",
        HTTP_HX_REQUEST="true",
    )
    assert response["HX-Redirect"] == r1.get_absolute_url()
