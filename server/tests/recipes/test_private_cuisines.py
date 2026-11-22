"""A user's own cuisines (#171, plan 012 M8).

`Cuisine.owner` is NULL for a node of the global, staff-curated tree, and a
user for a node private to that user, as tags and ingredients are. A typed
cuisine the user cannot see becomes theirs: under the nodes its path names,
or as an area of its own. Staff see them in the cuisine tool, and make one
global or merge it into the tree.
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse

from recipes.forms.field_forms import RecipeMetadataForm
from recipes.models import Cuisine, Recipe
from recipes.services.api_tokens import create_token
from recipes.services.cuisine_admin import CuisineOwnerError, delete_cuisines, merge_cuisines
from recipes.services.name_resolution import (
    CuisineNameError,
    cuisine_paths,
    find_cuisine,
    resolve_cuisine,
)
from recipes.services.recipe_document import parse_document
from recipes.services.recipe_import import import_recipes

MANAGE = "/recipes/cuisines/manage/"


def _node(path: str) -> Cuisine:
    node = find_cuisine(path)
    assert node is not None, path
    return node


@pytest.fixture
def italy() -> Cuisine:
    """The seeded global `med.italy`."""
    return _node("med.italy")


@pytest.fixture
def staff_client(user):
    """The default user, made staff, logged in."""
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    client = Client()
    client.force_login(user)
    return client


# --- Model -------------------------------------------------------------------


@pytest.mark.django_db
def test_two_users_may_each_have_a_private_cuisine_with_the_same_name(user, other_user, italy):
    """Private names only clash within one owner."""
    Cuisine.objects.create(cuisine="marche", parent=italy, owner=user)
    Cuisine.objects.create(cuisine="Marche", parent=italy, owner=other_user)
    Cuisine.objects.create(cuisine="nordic", owner=user)
    Cuisine.objects.create(cuisine="Nordic", owner=other_user)
    assert Cuisine.objects.filter(cuisine__iexact="marche").count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("inside", [True, False])
def test_one_user_cannot_have_two_siblings_differing_by_case(user, italy, inside):
    """Within one owner, sibling names are unique ignoring case, areas included."""
    parent = italy if inside else None
    Cuisine.objects.create(cuisine="marche", parent=parent, owner=user)
    with pytest.raises(IntegrityError), transaction.atomic():
        Cuisine.objects.create(cuisine="MARCHE", parent=parent, owner=user)


@pytest.mark.django_db
def test_a_private_cuisine_may_sit_inside_a_global_one_or_its_owners(user, italy):
    """The tree a user sees is the global one plus their own nodes."""
    nordic = Cuisine.objects.create(cuisine="nordic", owner=user)
    Cuisine(cuisine="marche", parent=italy, owner=user).full_clean()
    Cuisine(cuisine="sweden", parent=nordic, owner=user).full_clean()


@pytest.mark.django_db
def test_a_private_cuisine_cannot_sit_inside_another_users(user, other_user):
    """Nobody sees inside another user's cuisine."""
    nordic = Cuisine.objects.create(cuisine="nordic", owner=other_user)
    with pytest.raises(ValidationError, match="another user"):
        Cuisine(cuisine="sweden", parent=nordic, owner=user).full_clean()


@pytest.mark.django_db
def test_a_global_cuisine_cannot_sit_inside_a_private_one(user):
    """Every user sees the whole global tree, so none of it hides in a private node."""
    nordic = Cuisine.objects.create(cuisine="nordic", owner=user)
    with pytest.raises(ValidationError, match="private"):
        Cuisine(cuisine="sweden", parent=nordic).full_clean()


# --- Resolution --------------------------------------------------------------


@pytest.mark.django_db
def test_find_cuisine_sees_the_global_tree_and_the_owners_own(user, other_user, italy):
    """A path or a bare name, never another user's node, never the private ones for no owner."""
    marche = Cuisine.objects.create(cuisine="marche", parent=italy, owner=user)
    Cuisine.objects.create(cuisine="atlantis", owner=other_user)
    assert find_cuisine("med.italy.Marche", owner=user) == marche
    assert find_cuisine("marche", owner=user) == marche
    assert find_cuisine("med.italy.marche") is None
    assert find_cuisine("atlantis", owner=user) is None


@pytest.mark.django_db
def test_find_cuisine_prefers_a_global_node(user, italy):
    """A private node later shadowed by a global one of the same name loses to it."""
    Cuisine.objects.create(cuisine="marche", parent=italy, owner=user)
    marche = Cuisine.objects.create(cuisine="marche", parent=italy)
    assert find_cuisine("med.italy.marche", owner=user) == marche


@pytest.mark.django_db
def test_resolve_cuisine_finds_one_the_user_can_see(user):
    """Nothing is made for a cuisine already there."""
    before = Cuisine.objects.count()
    assert resolve_cuisine("Sicily", owner=user) == _node("med.italy.sicily")
    assert resolve_cuisine("", owner=user) is None
    assert Cuisine.objects.count() == before


@pytest.mark.django_db
def test_resolve_cuisine_makes_a_private_one_inside_the_path_it_names(user, italy):
    """`med.italy.marche` goes inside the global `med.italy`."""
    marche = resolve_cuisine("med.italy.Marche", owner=user)
    assert marche is not None
    assert (marche.cuisine, marche.parent, marche.owner) == ("Marche", italy, user)
    assert resolve_cuisine("med.italy.marche", owner=user) == marche


@pytest.mark.django_db
def test_resolve_cuisine_makes_each_missing_level(user):
    """`nordic.sweden` makes an area and a region of the user's own."""
    sweden = resolve_cuisine(" nordic . sweden ", owner=user)
    assert sweden is not None
    assert sweden.path == "nordic.sweden"
    assert sweden.parent_node is not None
    assert sweden.parent_node.owner == user
    assert sweden.owner == user


@pytest.mark.django_db
def test_resolve_cuisine_makes_an_unknown_bare_name_an_area(user):
    """A bare name nothing has becomes an area of the user's own."""
    fika = resolve_cuisine("fika", owner=user)
    assert fika is not None
    assert (fika.parent, fika.owner) == (None, user)


@pytest.mark.django_db
def test_resolve_cuisine_never_uses_another_users_node(user, other_user):
    """Another user's `atlantis` is invisible, so the user gets their own."""
    theirs = Cuisine.objects.create(cuisine="atlantis", owner=other_user)
    mine = resolve_cuisine("atlantis", owner=user)
    assert mine is not None
    assert mine != theirs
    assert mine.owner == user


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("text", "says"),
    [
        ("north", "More than one"),
        ("med.italy.sicily.palermo", "levels deep"),
        ("med..italy", "empty"),
        ("x" * 201, "characters"),
    ],
)
def test_resolve_cuisine_refuses_what_it_cannot_place(user, text, says):
    """An ambiguous bare name, a fourth level, a blank part or a long name makes nothing."""
    before = Cuisine.objects.count()
    with pytest.raises(CuisineNameError, match=says):
        resolve_cuisine(text, owner=user)
    assert Cuisine.objects.count() == before


@pytest.mark.django_db
def test_cuisine_paths_are_the_global_tree_and_the_owners_own(user, other_user, italy):
    """The suggestions a user is offered; no owner gets the global tree alone."""
    Cuisine.objects.create(cuisine="marche", parent=italy, owner=user)
    Cuisine.objects.create(cuisine="nordic", owner=other_user)
    assert "med.italy.marche" in cuisine_paths(owner=user)
    assert "nordic" not in cuisine_paths(owner=user)
    assert "med.italy.marche" not in cuisine_paths()


# --- The recipe editor ---------------------------------------------------------


def _data(**overrides: str) -> dict[str, str]:
    data = {
        "recipe_name": "Vincisgrassi",
        "short_description": "",
        "servings": "4",
        "source_instance": "",
        "cuisine_name": "",
        "tags": "",
    }
    return data | overrides


@pytest.mark.django_db
def test_new_recipe_makes_a_cuisine_of_the_owners_own(auth_client, user, italy):
    """Typing a cuisine the tree lacks makes it, as typing a tag does."""
    auth_client.post(reverse("recipes:new"), _data(cuisine_name="med.italy.marche"))
    recipe = Recipe.objects.get(recipe_name="Vincisgrassi")
    assert recipe.cuisine is not None
    assert (recipe.cuisine.path, recipe.cuisine.owner) == ("med.italy.marche", user)


@pytest.mark.django_db
def test_metadata_edit_makes_a_cuisine_of_the_owners_own(auth_client, user):
    """The metadata panel takes a new cuisine too."""
    recipe = Recipe.objects.create(recipe_name="Kanelbullar", owner=user, servings=4)
    auth_client.post(
        reverse("recipes:metadata_edit", kwargs={"recipe_id": recipe.pk}),
        _data(recipe_name="Kanelbullar", cuisine_name="nordic.sweden"),
        HTTP_HX_REQUEST="true",
    )
    recipe.refresh_from_db()
    assert recipe.cuisine is not None
    assert (recipe.cuisine.path, recipe.cuisine.owner) == ("nordic.sweden", user)


@pytest.mark.django_db
def test_form_refuses_a_cuisine_it_cannot_place(user):
    """An ambiguous bare name is a form error, and makes nothing."""
    before = Cuisine.objects.count()
    form = RecipeMetadataForm(data=_data(cuisine_name="north"), owner=user)
    assert not form.is_valid()
    assert "More than one" in form.errors["cuisine_name"][0]
    assert Cuisine.objects.count() == before


@pytest.mark.django_db
def test_a_form_that_does_not_save_makes_no_cuisine(auth_client):
    """The cuisine is made with the recipe, so a refused form leaves none behind."""
    before = Cuisine.objects.count()
    auth_client.post(reverse("recipes:new"), _data(recipe_name="", cuisine_name="atlantis"))
    assert not Recipe.objects.exists()
    assert Cuisine.objects.count() == before


@pytest.mark.django_db
def test_the_editor_offers_the_owners_own_cuisines(auth_client, user, other_user, italy):
    """The cuisine datalist holds the user's own paths, never another user's."""
    Cuisine.objects.create(cuisine="marche", parent=italy, owner=user)
    Cuisine.objects.create(cuisine="atlantis", owner=other_user)
    html = auth_client.get(reverse("recipes:new")).content.decode()
    assert 'value="med.italy.marche"' in html
    assert 'value="atlantis"' not in html


# --- Import and the clipper ------------------------------------------------------


@pytest.mark.django_db
def test_import_makes_a_cuisine_of_the_owners_own(user):
    """An imported cuisine the user cannot see becomes theirs, with no warning."""
    document = {
        "format": "nutrisho",
        "version": 1,
        "recipes": [{"recipe_name": "Soup", "cuisine": "atlantis.north"}],
    }
    result = import_recipes(owner=user, batch=parse_document(document))
    cuisine = Recipe.objects.get(owner=user).cuisine
    assert cuisine is not None
    assert (cuisine.path, cuisine.owner) == ("atlantis.north", user)
    assert result.warnings == []


@pytest.mark.django_db
def test_import_warns_of_a_cuisine_it_cannot_place(user):
    """An ambiguous name leaves the recipe without one, and says why."""
    document = {
        "format": "nutrisho",
        "version": 1,
        "recipes": [{"recipe_name": "Soup", "cuisine": "north"}],
    }
    result = import_recipes(owner=user, batch=parse_document(document))
    assert Recipe.objects.get(owner=user).cuisine is None
    assert len(result.warnings) == 1
    assert result.warnings[0].startswith("“Soup”: the cuisine “north” was left out:")
    assert "More than one" in result.warnings[0]


@pytest.mark.django_db
def test_the_clippers_lists_hold_the_users_own_cuisines(user, other_user, italy):
    """The vocabulary endpoint lists the user's own paths, never another user's."""
    Cuisine.objects.create(cuisine="marche", parent=italy, owner=user)
    Cuisine.objects.create(cuisine="atlantis", owner=other_user)
    key = create_token(user=user, name="clipper")[1]
    body = (
        Client().get("/recipes/api/vocabulary/", headers={"Authorization": f"Bearer {key}"}).json()
    )
    assert "med.italy.marche" in body["cuisines"]
    assert "atlantis" not in body["cuisines"]


# --- The staff cuisine tool ------------------------------------------------------


@pytest.mark.django_db
def test_the_tool_lists_a_private_cuisine_with_its_owner(staff_client, other_user, italy):
    """Staff see every user's cuisines, each marked whose it is."""
    Cuisine.objects.create(cuisine="marche", parent=italy, owner=other_user)
    html = staff_client.get(MANAGE, {"q": "marche"}).content.decode()
    assert "med.italy.marche" in html
    assert f"private to {other_user.username}" in html


@pytest.mark.django_db
def test_add_offers_only_global_parents(staff_client, other_user):
    """A node staff add is global, so it never goes inside a private one."""
    nordic = Cuisine.objects.create(cuisine="nordic", owner=other_user)
    html = staff_client.get(MANAGE + "add/").content.decode()
    assert f'value="{nordic.pk}"' not in html
    assert f'value="{_node("med").pk}"' in html


@pytest.mark.django_db
def test_edit_makes_a_private_cuisine_global(staff_client, other_user, italy):
    """Staff promote a user's cuisine into the shared tree."""
    marche = Cuisine.objects.create(cuisine="marche", parent=italy, owner=other_user)
    response = staff_client.post(
        f"{MANAGE}{marche.pk}/save/",
        {"cuisine": "marche", "parent": italy.pk, "make_global": "on"},
    )
    assert response.status_code == 200
    marche.refresh_from_db()
    assert marche.owner is None


@pytest.mark.django_db
def test_edit_keeps_a_private_cuisine_private_unless_asked(staff_client, other_user, italy):
    """Renaming a user's cuisine leaves it theirs."""
    marche = Cuisine.objects.create(cuisine="marche", parent=italy, owner=other_user)
    staff_client.post(f"{MANAGE}{marche.pk}/save/", {"cuisine": "Le Marche", "parent": italy.pk})
    marche.refresh_from_db()
    assert (marche.cuisine, marche.owner) == ("Le Marche", other_user)


@pytest.mark.django_db
def test_edit_refuses_to_make_global_a_cuisine_inside_a_private_one(staff_client, other_user):
    """Its private parent goes global first."""
    nordic = Cuisine.objects.create(cuisine="nordic", owner=other_user)
    sweden = Cuisine.objects.create(cuisine="sweden", parent=nordic, owner=other_user)
    response = staff_client.post(
        f"{MANAGE}{sweden.pk}/save/",
        {"cuisine": "sweden", "parent": nordic.pk, "make_global": "on"},
    )
    assert response.status_code == 422
    sweden.refresh_from_db()
    assert sweden.owner == other_user


@pytest.mark.django_db
def test_merge_moves_a_private_cuisine_into_the_tree(user, other_user, italy):
    """Staff fold a user's cuisine into a global one, and the user's recipes follow."""
    marche = Cuisine.objects.create(cuisine="marche", parent=italy, owner=other_user)
    recipe = Recipe.objects.create(recipe_name="Vincisgrassi", owner=other_user, cuisine=marche)
    merge_cuisines(survivor_id=italy.pk, victim_ids=[marche.pk])
    recipe.refresh_from_db()
    assert recipe.cuisine == italy
    assert not Cuisine.objects.filter(pk=marche.pk).exists()


@pytest.mark.django_db
def test_merge_refuses_a_private_survivor_for_others_recipes(user, other_user, italy):
    """No user's recipe ends up on a cuisine they cannot see."""
    marche = Cuisine.objects.create(cuisine="marche", parent=italy, owner=other_user)
    with pytest.raises(CuisineOwnerError):
        merge_cuisines(survivor_id=marche.pk, victim_ids=[_node("med.italy.sicily").pk])
    assert Cuisine.objects.filter(pk=marche.pk).exists()


@pytest.mark.django_db
def test_merge_takes_a_private_survivor_for_the_same_owners_cuisines(other_user, italy):
    """Two of one user's own cuisines may be merged either way."""
    marche = Cuisine.objects.create(cuisine="marche", parent=italy, owner=other_user)
    marches = Cuisine.objects.create(cuisine="marches", parent=italy, owner=other_user)
    merge_cuisines(survivor_id=marche.pk, victim_ids=[marches.pk])
    assert not Cuisine.objects.filter(pk=marches.pk).exists()


@pytest.mark.django_db
def test_delete_refuses_a_private_replacement_for_others_recipes(user, other_user, italy):
    """The same rule for Delete's replacement."""
    marche = Cuisine.objects.create(cuisine="marche", parent=italy, owner=other_user)
    sicily = _node("med.italy.sicily")
    with pytest.raises(CuisineOwnerError):
        delete_cuisines(cuisine_ids=[sicily.pk], replacement_id=marche.pk)
    assert Cuisine.objects.filter(pk=sicily.pk).exists()


@pytest.mark.django_db
def test_the_merge_view_says_why_it_refused(staff_client, other_user, italy):
    """A private survivor for global nodes comes back as the form's error."""
    marche = Cuisine.objects.create(cuisine="marche", parent=italy, owner=other_user)
    sicily = _node("med.italy.sicily")
    response = staff_client.post(
        MANAGE + "merge/",
        {"cuisine_ids": [marche.pk, sicily.pk], "survivor_id": marche.pk},
    )
    assert response.status_code == 422
    assert "private to" in response.content.decode()
