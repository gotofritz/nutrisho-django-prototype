"""Soft-deleted recipes: the trash, Undo and restore (#75)."""

import pytest
from django.test import Client
from django.utils import timezone

from recipes.models import Cuisine, Recipe, Step, Tag
from recipes.services.recipe_metadata import create_recipe
from recipes.services.recipe_search import (
    RecipeSearch,
    cuisine_choices,
    search_recipes,
    tag_choices,
)
from recipes.services.recipe_trash import (
    purge_recipe,
    restore_recipe,
    trash_recipe,
    trashed_recipes,
)


@pytest.fixture
def recipe(user, make_recipe):
    """A live recipe of `user`'s."""
    return make_recipe(owner=user, name="Soup")


@pytest.fixture
def trashed(user, make_recipe):
    """A recipe of `user`'s already in the trash."""
    recipe = make_recipe(owner=user, name="Old stew")
    trash_recipe(recipe)
    return recipe


@pytest.fixture
def other_client(other_user):
    """A client signed in as a user who owns nothing here."""
    c = Client()
    c.force_login(other_user)
    return c


# --- Services ---


@pytest.mark.django_db
def test_trash_recipe_keeps_the_row_and_its_contents(recipe, add_step):
    """Trashing stamps deleted_at; the recipe and its steps stay in the database."""
    add_step(recipe=recipe, text="Stir")
    trash_recipe(recipe)
    recipe.refresh_from_db()
    assert recipe.deleted_at is not None
    assert Step.objects.filter(recipe=recipe).count() == 1


@pytest.mark.django_db
def test_live_and_trashed_querysets_split_recipes(recipe, trashed):
    """`live()` and `trashed()` partition the recipes."""
    assert list(Recipe.objects.live()) == [recipe]
    assert list(Recipe.objects.trashed()) == [trashed]


@pytest.mark.django_db
def test_search_leaves_out_trashed_recipes(user, recipe, trashed):
    """The list and its search never show a trashed recipe."""
    assert list(search_recipes(owner=user, search=RecipeSearch())) == [recipe]
    assert list(search_recipes(owner=user, search=RecipeSearch(query="stew"))) == []


@pytest.mark.django_db
def test_filter_choices_leave_out_cuisines_and_tags_only_trashed_recipes_use(user, recipe, trashed):
    """A cuisine or tag on trashed recipes alone would filter the list to nothing."""
    trashed.cuisine = Cuisine.objects.create(cuisine="Thai")
    trashed.save(update_fields=["cuisine"])
    Tag.objects.create(tag="hearty").recipes.add(trashed)
    assert cuisine_choices(user) == []
    assert tag_choices(user) == []


@pytest.mark.django_db
def test_a_trashed_name_is_free_for_a_new_recipe(user, trashed):
    """The per-owner name rule applies to live recipes only."""
    created = create_recipe(owner=user, recipe=Recipe(recipe_name="Old stew"), tag_names=[])
    assert created.pk != trashed.pk


@pytest.mark.django_db
def test_restore_recipe_brings_it_back(trashed):
    """Restore clears deleted_at and keeps the name."""
    restored = restore_recipe(trashed)
    restored.refresh_from_db()
    assert restored.deleted_at is None
    assert restored.recipe_name == "Old stew"


@pytest.mark.django_db
def test_restore_renames_when_a_live_recipe_took_the_name(user, make_recipe, trashed):
    """A clash with a live recipe gets the restored one a "Restored" suffix."""
    make_recipe(owner=user, name="Old stew")
    restored = restore_recipe(trashed)
    restored.refresh_from_db()
    assert restored.recipe_name == "Old stew Restored"
    assert restored.deleted_at is None


@pytest.mark.django_db
def test_restore_numbers_the_suffix_on_a_second_clash(user, make_recipe, trashed):
    """A second clash counts up, as duplicate names do."""
    make_recipe(owner=user, name="Old stew")
    make_recipe(owner=user, name="Old stew Restored")
    restored = restore_recipe(trashed)
    assert restored.recipe_name == "Old stew Restored 2"


@pytest.mark.django_db
def test_trashed_recipes_lists_the_owners_newest_first(user, other_user, make_recipe):
    """Most recently deleted first; another user's trash is not listed."""
    first = make_recipe(owner=user, name="First")
    second = make_recipe(owner=user, name="Second")
    theirs = make_recipe(owner=other_user, name="Theirs")
    for r in (first, second, theirs):
        trash_recipe(r)
    Recipe.objects.filter(pk=first.pk).update(deleted_at=timezone.now())
    assert list(trashed_recipes(owner=user)) == [first, second]


@pytest.mark.django_db
def test_purge_recipe_deletes_it_for_good(trashed):
    """Purge removes the row."""
    purge_recipe(trashed)
    assert not Recipe.objects.filter(pk=trashed.pk).exists()


# --- Delete moves to the trash ---


@pytest.mark.django_db
def test_delete_view_moves_the_recipe_to_the_trash(auth_client, recipe):
    """Delete no longer removes the row."""
    response = auth_client.post(f"/recipes/{recipe.pk}/delete/", HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    recipe.refresh_from_db()
    assert recipe.deleted_at is not None


@pytest.mark.django_db
def test_delete_goes_on_to_the_next_live_recipe(auth_client, user, make_recipe):
    """A trashed neighbour is skipped."""
    mid = make_recipe(owner=user, name="Mid")
    trash_recipe(make_recipe(owner=user, name="Gone"))
    nxt = make_recipe(owner=user, name="Next")
    response = auth_client.post(f"/recipes/{mid.pk}/delete/", HTTP_HX_REQUEST="true")
    assert response["HX-Redirect"] == nxt.get_absolute_url()


@pytest.mark.django_db
def test_the_next_page_offers_undo(auth_client, recipe):
    """The page after a delete names the recipe and posts Undo to its restore URL."""
    auth_client.post(f"/recipes/{recipe.pk}/delete/", HTTP_HX_REQUEST="true")
    page = auth_client.get("/recipes/").content.decode()
    assert "Deleted “Soup”." in page
    assert f'action="/recipes/{recipe.pk}/restore/"' in page
    assert ">Undo</button>" in page


@pytest.mark.django_db
def test_undo_is_offered_once(auth_client, recipe):
    """The toast goes once it has been shown."""
    auth_client.post(f"/recipes/{recipe.pk}/delete/", HTTP_HX_REQUEST="true")
    auth_client.get("/recipes/")
    assert ">Undo</button>" not in auth_client.get("/recipes/").content.decode()


@pytest.mark.django_db
def test_delete_panel_says_the_recipe_can_be_restored(auth_client, recipe):
    """The confirmation no longer says the delete is final."""
    page = auth_client.get(
        f"/recipes/{recipe.pk}/delete/panel/", HTTP_HX_REQUEST="true"
    ).content.decode()
    assert "cannot be undone" not in page
    assert "trash" in page


# --- A trashed recipe is out of reach ---


@pytest.mark.django_db
def test_trashed_recipe_page_is_404(auth_client, trashed):
    """Its page is gone until it is restored."""
    assert auth_client.get(f"/recipes/{trashed.pk}/").status_code == 404


@pytest.mark.django_db
def test_trashed_recipe_cannot_be_edited(auth_client, trashed):
    """Every edit endpoint loads through owned_recipe, which skips the trash."""
    response = auth_client.post(
        f"/recipes/{trashed.pk}/field/recipe_name/save/",
        {"recipe_name": "Renamed"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 404
    trashed.refresh_from_db()
    assert trashed.recipe_name == "Old stew"


@pytest.mark.django_db
def test_list_leaves_out_trashed_recipes(auth_client, recipe, trashed):
    """The recipe list shows live recipes only."""
    page = auth_client.get("/recipes/").content.decode()
    assert "Soup" in page
    assert "Old stew" not in page


# --- The trash page ---


@pytest.mark.django_db
def test_trash_page_lists_trashed_recipes_with_restore_and_purge(auth_client, recipe, trashed):
    """Each trashed recipe can be restored or deleted for good."""
    response = auth_client.get("/recipes/trash/")
    assert response.status_code == 200
    page = response.content.decode()
    assert "Old stew" in page
    assert "Soup" not in page
    assert f'action="/recipes/{trashed.pk}/restore/"' in page
    assert f'action="/recipes/{trashed.pk}/purge/"' in page


@pytest.mark.django_db
def test_trash_page_says_when_it_is_empty(auth_client, recipe):
    """An empty trash says so."""
    assert "The trash is empty." in auth_client.get("/recipes/trash/").content.decode()


@pytest.mark.django_db
def test_trash_page_hides_other_users_recipes(other_client, trashed):
    """Another user's trash is private."""
    assert "Old stew" not in other_client.get("/recipes/trash/").content.decode()


@pytest.mark.django_db
def test_site_header_links_to_the_trash(auth_client, recipe):
    """The trash is reachable from every page."""
    assert 'href="/recipes/trash/"' in auth_client.get("/recipes/").content.decode()


# --- Restore ---


@pytest.mark.django_db
def test_restore_view_brings_the_recipe_back_and_opens_it(auth_client, trashed):
    """Restore (or Undo) goes to the restored recipe."""
    response = auth_client.post(f"/recipes/{trashed.pk}/restore/", HTTP_HX_REQUEST="true")
    assert response["HX-Redirect"] == trashed.get_absolute_url()
    trashed.refresh_from_db()
    assert trashed.deleted_at is None


@pytest.mark.django_db
def test_restore_view_plain_post_redirects(auth_client, trashed):
    """Without htmx the restore is a plain redirect."""
    response = auth_client.post(f"/recipes/{trashed.pk}/restore/")
    assert response.status_code == 302
    assert response["Location"] == trashed.get_absolute_url()


@pytest.mark.django_db
def test_restore_view_says_what_it_restored(auth_client, trashed):
    """The recipe page confirms the restore."""
    auth_client.post(f"/recipes/{trashed.pk}/restore/")
    assert "Restored “Old stew”." in auth_client.get(trashed.get_absolute_url()).content.decode()


@pytest.mark.django_db
def test_restore_view_refuses_another_users_recipe(other_client, trashed):
    """404, and the recipe stays in the trash."""
    response = other_client.post(f"/recipes/{trashed.pk}/restore/", HTTP_HX_REQUEST="true")
    assert response.status_code == 404
    trashed.refresh_from_db()
    assert trashed.deleted_at is not None


@pytest.mark.django_db
def test_restore_view_404s_on_a_live_recipe(auth_client, recipe):
    """Only a trashed recipe can be restored."""
    assert auth_client.post(f"/recipes/{recipe.pk}/restore/").status_code == 404


@pytest.mark.django_db
def test_restore_view_rejects_get(auth_client, trashed):
    """Restore writes, so it is POST only."""
    assert auth_client.get(f"/recipes/{trashed.pk}/restore/").status_code == 405


# --- Purge ---


@pytest.mark.django_db
def test_purge_view_deletes_for_good_and_returns_to_the_trash(auth_client, trashed):
    """Delete forever removes the row and goes back to the trash page."""
    response = auth_client.post(f"/recipes/{trashed.pk}/purge/")
    assert response.status_code == 302
    assert response["Location"] == "/recipes/trash/"
    assert not Recipe.objects.filter(pk=trashed.pk).exists()


@pytest.mark.django_db
def test_purge_view_htmx_redirects_to_the_trash(auth_client, trashed):
    """An htmx purge navigates with HX-Redirect."""
    response = auth_client.post(f"/recipes/{trashed.pk}/purge/", HTTP_HX_REQUEST="true")
    assert response["HX-Redirect"] == "/recipes/trash/"


@pytest.mark.django_db
def test_purge_view_refuses_a_live_recipe(auth_client, recipe):
    """A live recipe has to go through the trash first."""
    assert auth_client.post(f"/recipes/{recipe.pk}/purge/").status_code == 404
    assert Recipe.objects.filter(pk=recipe.pk).exists()


@pytest.mark.django_db
def test_purge_view_refuses_another_users_recipe(other_client, trashed):
    """404, and nothing is deleted."""
    assert other_client.post(f"/recipes/{trashed.pk}/purge/").status_code == 404
    assert Recipe.objects.filter(pk=trashed.pk).exists()
