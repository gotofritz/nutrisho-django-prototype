"""The ingredient clean-up tool is staff-only (#46).

`Ingredient` rows are shared by every account, so a rename, merge or delete in
the tool reaches recipes the acting user does not own. Any signed-in user who is
not staff gets a 403 on every route, and a mutating route writes nothing.
"""

import pytest

from recipes.models import Ingredient

MANAGE = "/recipes/ingredients/manage/"


@pytest.fixture
def staff_client(user):
    """The default user, made staff, logged in."""
    from django.test import Client

    user.is_staff = True
    user.save(update_fields=["is_staff"])
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def other_client(other_user):
    """A signed-in user who is not staff."""
    from django.test import Client

    client = Client()
    client.force_login(other_user)
    return client


@pytest.fixture
def pair(make_ingredient, make_recipe, add_ingredient, user):
    """Two ingredients, both used by a recipe the default user owns."""
    onion = make_ingredient("onion")
    onions = make_ingredient("onions")
    recipe = make_recipe(owner=user, name="Soup")
    add_ingredient(recipe=recipe, ingredient=onion)
    add_ingredient(recipe=recipe, ingredient=onions)
    return onion, onions


def _read_routes(recipe_id: int) -> list[str]:
    return [
        MANAGE,
        MANAGE + "search/",
        MANAGE + "recipes/",
        MANAGE + f"preview/{recipe_id}/",
        MANAGE + "cancel/",
        MANAGE + "edit/",
        MANAGE + "delete/",
        MANAGE + "merge/",
        MANAGE + "merge-plural/",
        MANAGE + "promote/",
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("htmx", [False, True], ids=["page", "htmx"])
def test_every_read_route_is_forbidden_to_non_staff(other_client, pair, htmx):
    """GET routes answer 403 to a signed-in user who is not staff."""
    onion, onions = pair
    recipe_id = onion.pk  # any int; the guard runs before the lookup
    headers = {"HTTP_HX_REQUEST": "true"} if htmx else {}
    for url in _read_routes(recipe_id):
        response = other_client.get(url, {"ingredient_ids": [onion.pk, onions.pk]}, **headers)
        assert response.status_code == 403, url


@pytest.mark.django_db
def test_save_is_forbidden_to_non_staff_and_writes_nothing(other_client, pair):
    """Renaming an ingredient is refused and the name is unchanged."""
    onion, _ = pair
    response = other_client.post(
        MANAGE + f"{onion.pk}/save/",
        {"ingredient_name": "shallot", "ingredient_ids": [onion.pk]},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 403
    onion.refresh_from_db()
    assert onion.ingredient_name == "onion"


@pytest.mark.django_db
def test_delete_is_forbidden_to_non_staff_and_writes_nothing(other_client, pair):
    """Deleting is refused and both rows survive."""
    onion, onions = pair
    response = other_client.post(
        MANAGE + "delete/",
        {"ingredient_ids": [onions.pk], "replacement_id": onion.pk},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 403
    assert Ingredient.objects.filter(pk__in=[onion.pk, onions.pk]).count() == 2


@pytest.mark.django_db
def test_merge_is_forbidden_to_non_staff_and_writes_nothing(other_client, pair):
    """Merging is refused and both rows survive."""
    onion, onions = pair
    response = other_client.post(
        MANAGE + "merge/",
        {"ingredient_ids": [onion.pk, onions.pk], "survivor_id": onion.pk},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 403
    assert Ingredient.objects.filter(pk__in=[onion.pk, onions.pk]).count() == 2


@pytest.mark.django_db
def test_merge_plural_is_forbidden_to_non_staff_and_writes_nothing(other_client, pair):
    """Merging a plural is refused: both rows survive and no plural is written."""
    onion, onions = pair
    response = other_client.post(
        MANAGE + "merge-plural/",
        {"ingredient_ids": [onion.pk, onions.pk], "singular_id": onion.pk},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 403
    assert Ingredient.objects.filter(pk__in=[onion.pk, onions.pk]).count() == 2
    onion.refresh_from_db()
    assert onion.plural_name == ""


@pytest.mark.django_db
def test_promote_is_forbidden_to_non_staff_and_writes_nothing(other_client, other_user):
    """Promoting is refused and the row stays private."""
    yuzu = Ingredient.objects.create(ingredient_name="yuzu", owner=other_user)
    response = other_client.post(
        MANAGE + "promote/", {"ingredient_ids": [yuzu.pk]}, HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 403
    yuzu.refresh_from_db()
    assert yuzu.owner == other_user


@pytest.mark.django_db
def test_htmx_403_is_a_short_fragment_not_a_page(other_client):
    """An htmx request gets a bare message, never a whole page to swap in."""
    response = other_client.get(MANAGE + "search/", HTTP_HX_REQUEST="true")
    assert response.status_code == 403
    assert b"<html" not in response.content.lower()


@pytest.mark.django_db
def test_page_403_explains_and_links_home(other_client):
    """A full-page visit gets a page saying the tool is staff-only."""
    response = other_client.get(MANAGE)
    html = response.content.decode()
    assert response.status_code == 403
    assert "staff" in html.lower()
    assert 'href="/recipes/"' in html


@pytest.mark.django_db
def test_anonymous_user_is_still_sent_to_login(client):
    """Signing in comes before the staff check."""
    response = client.get(MANAGE)
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_staff_can_open_the_tool(staff_client):
    """Staff reach the tool."""
    assert staff_client.get(MANAGE).status_code == 200


@pytest.mark.django_db
def test_staff_can_merge(staff_client, pair):
    """A staff merge goes through."""
    onion, onions = pair
    response = staff_client.post(
        MANAGE + "merge/",
        {"ingredient_ids": [onion.pk, onions.pk], "survivor_id": onion.pk},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert not Ingredient.objects.filter(pk=onions.pk).exists()


@pytest.mark.django_db
def test_home_hides_the_manage_link_from_non_staff(other_client):
    """Non-staff see no link to a tool they cannot open."""
    html = other_client.get("/recipes/").content.decode()
    assert MANAGE not in html


@pytest.mark.django_db
def test_home_shows_the_manage_link_to_staff(staff_client):
    """Staff see the link."""
    html = staff_client.get("/recipes/").content.decode()
    assert MANAGE in html
