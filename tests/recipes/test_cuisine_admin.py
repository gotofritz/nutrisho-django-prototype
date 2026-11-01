"""The staff-only cuisine tool and the cuisine on the recipe page (plan 011, PR 4).

The tool mirrors the ingredient clean-up tool: a searchable list of every node
of the cuisine tree, the staff member's recipes using the selection, and Add,
Edit, Merge and Delete actions.
"""

import pytest
from django.test import Client

from recipes.models import Cuisine, Recipe
from recipes.services.name_resolution import find_cuisine

MANAGE = "/recipes/cuisines/manage/"


def _node(path: str) -> Cuisine:
    node = find_cuisine(path)
    assert node is not None, path
    return node


@pytest.fixture
def staff_client(user):
    """The default user, made staff, logged in."""
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def other_client(other_user):
    """A signed-in user who is not staff."""
    client = Client()
    client.force_login(other_user)
    return client


# --- Recipe page -----------------------------------------------------------------


@pytest.mark.django_db
def test_recipe_page_shows_the_cuisine_but_not_in_print(auth_client, user):
    """The cuisine path sits in the description block, marked no-print."""
    recipe = Recipe.objects.create(
        recipe_name="Caponata", owner=user, cuisine=_node("med.italy.sicily")
    )
    html = auth_client.get(f"/recipes/{recipe.pk}/").content.decode()
    assert 'class="recipe-cuisine no-print"' in html
    assert "med.italy.sicily" in html


@pytest.mark.django_db
def test_recipe_page_without_a_cuisine_shows_no_cuisine_line(auth_client, user):
    """No cuisine, no line."""
    recipe = Recipe.objects.create(recipe_name="Toast", owner=user)
    assert "recipe-cuisine" not in auth_client.get(f"/recipes/{recipe.pk}/").content.decode()


# --- Access ----------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url", ["", "columns/", "add/", "edit/", "merge/", "delete/"], ids=lambda u: u or "page"
)
def test_every_read_route_is_staff_only(other_client, url):
    """Non-staff get 403 on every GET route."""
    assert other_client.get(MANAGE + url).status_code == 403


@pytest.mark.django_db
def test_mutations_are_staff_only_and_write_nothing(other_client, user):
    """Non-staff POSTs are refused before anything is written."""
    italy = _node("med.italy")
    before = Cuisine.objects.count()
    for url, data in [
        ("add/", {"cuisine": "x", "parent": italy.pk}),
        (f"{italy.pk}/save/", {"cuisine": "renamed"}),
        ("merge/", {"cuisine_ids": [italy.pk, _node("med.spain").pk], "survivor_id": italy.pk}),
        ("delete/", {"cuisine_ids": [_node("med.malta").pk]}),
    ]:
        assert other_client.post(MANAGE + url, data).status_code == 403, url
    assert Cuisine.objects.count() == before
    italy.refresh_from_db()
    assert italy.cuisine == "italy"


@pytest.mark.django_db
def test_home_links_the_tool_for_staff_only(staff_client, other_client):
    """The link sits next to "Manage ingredients", for staff only."""
    assert MANAGE in staff_client.get("/recipes/").content.decode()
    assert MANAGE not in other_client.get("/recipes/").content.decode()


# --- Browsing --------------------------------------------------------------------


@pytest.mark.django_db
def test_page_lists_every_node_by_path(staff_client):
    """Every node appears, as its full path."""
    html = staff_client.get(MANAGE).content.decode()
    assert "med.italy.sicily" in html
    assert html.count('class="cuisine-pick"') == Cuisine.objects.count()


@pytest.mark.django_db
def test_search_narrows_the_list(staff_client):
    """`?q=` keeps paths containing the text."""
    html = staff_client.get(MANAGE + "columns/", {"q": "sicil"}).content.decode()
    assert html.count('class="cuisine-pick"') == 1


@pytest.mark.django_db
def test_selection_lists_the_staff_members_recipes(staff_client, user, other_user):
    """Column 3 shows the user's own recipes using the selection."""
    sicily = _node("med.italy.sicily")
    Recipe.objects.create(recipe_name="Caponata", owner=user, cuisine=sicily)
    Recipe.objects.create(recipe_name="Hidden", owner=other_user, cuisine=sicily)
    html = staff_client.get(MANAGE + "columns/", {"cuisine_ids": [sicily.pk]}).content.decode()
    assert "Caponata" in html
    assert "Hidden" not in html


# --- Add / Edit ------------------------------------------------------------------


@pytest.mark.django_db
def test_add_creates_a_node_under_its_parent(staff_client):
    """Staff add anglo.canada.quebec."""
    response = staff_client.post(
        MANAGE + "add/", {"cuisine": "quebec", "parent": _node("anglo.canada").pk}
    )
    assert response.status_code == 200
    assert find_cuisine("anglo.canada.quebec") is not None


@pytest.mark.django_db
def test_add_refuses_a_fourth_level(staff_client):
    """The depth limit is a form error (422), and nothing is written."""
    before = Cuisine.objects.count()
    response = staff_client.post(
        MANAGE + "add/", {"cuisine": "palermo", "parent": _node("med.italy.sicily").pk}
    )
    assert response.status_code == 422
    assert Cuisine.objects.count() == before


@pytest.mark.django_db
def test_add_refuses_a_sibling_clash(staff_client):
    """A second `Sicily` under italy is a form error, not a 500."""
    response = staff_client.post(
        MANAGE + "add/", {"cuisine": "Sicily", "parent": _node("med.italy").pk}
    )
    assert response.status_code == 422


@pytest.mark.django_db
def test_edit_needs_exactly_one_selected(staff_client):
    """Edit works on one node at a time."""
    ids = [_node("med.italy").pk, _node("med.spain").pk]
    assert staff_client.get(MANAGE + "edit/", {"cuisine_ids": ids}).status_code == 422
    assert staff_client.get(MANAGE + "edit/", {"cuisine_ids": ids[:1]}).status_code == 200


@pytest.mark.django_db
def test_edit_renames_and_moves_a_node(staff_client):
    """Renaming and re-parenting go through the model's validation."""
    malta = _node("med.malta")
    response = staff_client.post(
        MANAGE + f"{malta.pk}/save/", {"cuisine": "malta", "parent": _node("eu").pk}
    )
    assert response.status_code == 200
    assert find_cuisine("eu.malta") == malta


@pytest.mark.django_db
def test_edit_refuses_a_move_that_breaks_the_depth_limit(staff_client):
    """Moving italy (with regions) under spain would put sicily four deep."""
    italy = _node("med.italy")
    response = staff_client.post(
        MANAGE + f"{italy.pk}/save/", {"cuisine": "italy", "parent": _node("med.spain").pk}
    )
    assert response.status_code == 422
    assert find_cuisine("med.italy") == italy


# --- Merge -----------------------------------------------------------------------


@pytest.mark.django_db
def test_merge_moves_recipes_to_the_survivor(staff_client, user, other_user):
    """Every owner's recipes follow; the other nodes go."""
    keep = _node("med.balkans.serbia")
    gone = Cuisine.objects.create(cuisine="Serbian", parent=None)
    mine = Recipe.objects.create(recipe_name="Ćevapi", owner=user, cuisine=gone)
    theirs = Recipe.objects.create(recipe_name="Ajvar", owner=other_user, cuisine=gone)
    response = staff_client.post(
        MANAGE + "merge/", {"cuisine_ids": [keep.pk, gone.pk], "survivor_id": keep.pk}
    )
    assert response.status_code == 200
    assert not Cuisine.objects.filter(pk=gone.pk).exists()
    for recipe in (mine, theirs):
        recipe.refresh_from_db()
        assert recipe.cuisine == keep


@pytest.mark.django_db
def test_merge_refuses_a_node_with_children(staff_client):
    """Merging away italy would orphan its regions: 422, nothing written."""
    italy, spain = _node("med.italy"), _node("med.spain")
    response = staff_client.post(
        MANAGE + "merge/", {"cuisine_ids": [italy.pk, spain.pk], "survivor_id": spain.pk}
    )
    assert response.status_code == 422
    assert Cuisine.objects.filter(pk=italy.pk).exists()


@pytest.mark.django_db
def test_merge_needs_a_survivor_from_the_selection(staff_client):
    """No survivor, no merge."""
    a, b = _node("med.malta"), _node("med.portugal")
    response = staff_client.post(MANAGE + "merge/", {"cuisine_ids": [a.pk, b.pk]})
    assert response.status_code == 422


# --- Delete ----------------------------------------------------------------------


@pytest.mark.django_db
def test_delete_with_a_replacement_moves_recipes(staff_client, user):
    """Recipes move to the replacement before the node goes."""
    malta = _node("med.malta")
    recipe = Recipe.objects.create(recipe_name="Pastizzi", owner=user, cuisine=malta)
    staff_client.post(
        MANAGE + "delete/", {"cuisine_ids": [malta.pk], "replacement_id": _node("med").pk}
    )
    recipe.refresh_from_db()
    assert recipe.cuisine == _node("med")
    assert not Cuisine.objects.filter(pk=malta.pk).exists()


@pytest.mark.django_db
def test_delete_without_a_replacement_clears_the_cuisine(staff_client, user):
    """With no replacement, recipes keep no cuisine."""
    malta = _node("med.malta")
    recipe = Recipe.objects.create(recipe_name="Pastizzi", owner=user, cuisine=malta)
    staff_client.post(MANAGE + "delete/", {"cuisine_ids": [malta.pk]})
    recipe.refresh_from_db()
    assert recipe.cuisine is None


@pytest.mark.django_db
def test_delete_refuses_a_node_with_children(staff_client):
    """Deleting italy would orphan its regions: 422, nothing written."""
    italy = _node("med.italy")
    response = staff_client.post(MANAGE + "delete/", {"cuisine_ids": [italy.pk]})
    assert response.status_code == 422
    assert Cuisine.objects.filter(pk=italy.pk).exists()


@pytest.mark.django_db
def test_delete_confirmation_counts_every_owners_recipes(staff_client, user, other_user):
    """The confirmation warns about recipes the staff member cannot see."""
    malta = _node("med.malta")
    Recipe.objects.create(recipe_name="A", owner=user, cuisine=malta)
    Recipe.objects.create(recipe_name="B", owner=other_user, cuisine=malta)
    html = staff_client.get(MANAGE + "delete/", {"cuisine_ids": [malta.pk]}).content.decode()
    assert "2 recipes" in html
