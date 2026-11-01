"""Private ingredients and promoting them to global (plan 011, PR 2).

`Ingredient.owner` is NULL for the global, staff-curated list and a user for a
row private to that user. Typing an unknown name in the recipe editor creates a
private row; staff promote it, which makes it global and folds every other
user's same-named private row into it.
"""

import pytest
from django.db import IntegrityError, transaction

from recipes.forms.ingredient_admin_forms import IngredientForm
from recipes.models import Ingredient, IngredientInRecipe
from recipes.services.ingredient_admin import (
    IngredientScopeError,
    delete_ingredients,
    merge_ingredients,
    promote_ingredients,
    search_ingredients,
)
from recipes.services.name_resolution import (
    find_ingredient,
    ingredient_names_for,
    resolve_ingredient,
)


@pytest.fixture
def private(db):
    """Make a row private to `owner`."""

    def _make(name: str, *, owner) -> Ingredient:
        return Ingredient.objects.create(ingredient_name=name, owner=owner)

    return _make


# --- Model -------------------------------------------------------------------


@pytest.mark.django_db
def test_existing_style_rows_are_global(make_ingredient):
    """A row made without an owner is global."""
    assert make_ingredient("onion").owner is None


@pytest.mark.django_db
def test_two_users_may_each_have_a_private_row_with_the_same_name(private, user, other_user):
    """Private names only clash within one owner."""
    private("yuzu", owner=user)
    private("Yuzu", owner=other_user)
    assert Ingredient.objects.filter(ingredient_name__iexact="yuzu").count() == 2


@pytest.mark.django_db
def test_one_user_cannot_have_two_private_rows_differing_by_case(private, user):
    """Within one owner, names are unique ignoring case."""
    private("yuzu", owner=user)
    with pytest.raises(IntegrityError), transaction.atomic():
        private("YUZU", owner=user)


@pytest.mark.django_db
def test_two_global_rows_cannot_differ_by_case_only(make_ingredient):
    """The global list keeps its case-insensitive uniqueness."""
    make_ingredient("onion")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_ingredient("Onion")


@pytest.mark.django_db
def test_deleting_a_user_deletes_their_private_rows(private, other_user):
    """Private rows go with their owner (their recipes go too)."""
    private("yuzu", owner=other_user)
    other_user.delete()
    assert not Ingredient.objects.exists()


# --- Resolution --------------------------------------------------------------


@pytest.mark.django_db
def test_resolve_prefers_the_global_row(make_ingredient, user):
    """A global name resolves to the global row, never a private copy."""
    onion = make_ingredient("onion")
    assert resolve_ingredient("Onion", owner=user) == onion
    assert Ingredient.objects.count() == 1


@pytest.mark.django_db
def test_resolve_finds_the_users_own_private_row(private, user):
    """A user's own private row is reused."""
    yuzu = private("yuzu", owner=user)
    assert resolve_ingredient("YUZU", owner=user) == yuzu


@pytest.mark.django_db
def test_resolve_never_returns_another_users_private_row(private, user, other_user):
    """Another user's private row is invisible: the user gets their own."""
    theirs = private("yuzu", owner=other_user)
    mine = resolve_ingredient("yuzu", owner=user)
    assert mine != theirs
    assert mine.owner == user


@pytest.mark.django_db
def test_resolve_creates_a_private_row_on_a_miss(user):
    """An unknown name becomes private to the user who typed it."""
    created = resolve_ingredient(" Yuzu ", owner=user)
    assert created.ingredient_name == "Yuzu"
    assert created.owner == user


@pytest.mark.django_db
def test_find_sees_global_and_own_rows_only(make_ingredient, private, user, other_user):
    """`find_ingredient` looks in the same two places and never creates."""
    onion = make_ingredient("onion")
    yuzu = private("yuzu", owner=user)
    private("sumac", owner=other_user)
    assert find_ingredient("ONION", owner=user) == onion
    assert find_ingredient("yuzu", owner=user) == yuzu
    assert find_ingredient("sumac", owner=user) is None
    assert Ingredient.objects.count() == 3


@pytest.mark.django_db
def test_suggestions_are_global_plus_own(make_ingredient, private, user, other_user):
    """The editor's datalist never leaks another user's private names."""
    make_ingredient("onion")
    private("yuzu", owner=user)
    private("sumac", owner=other_user)
    assert ingredient_names_for(user) == ["onion", "yuzu"]


# --- Recipe editor -----------------------------------------------------------


@pytest.fixture
def group(make_recipe, user):
    """A group in a recipe the default user owns."""
    from recipes.models import IngredientGroup

    recipe = make_recipe(owner=user, name="Salad")
    return IngredientGroup.objects.create(recipe=recipe, group_name="", index_in_sequence=0)


@pytest.mark.django_db
def test_editor_creates_an_unknown_ingredient_as_private(auth_client, group, user):
    """Adding an unknown ingredient in the editor makes it the owner's."""
    url = f"/recipes/{group.recipe.pk}/groups/{group.pk}/ingredients/create/"
    response = auth_client.post(url, {"ingredient_name": "yuzu"})
    assert response.status_code == 200
    assert Ingredient.objects.get(ingredient_name="yuzu").owner == user


@pytest.mark.django_db
def test_editor_links_a_known_global_ingredient(auth_client, group, make_ingredient):
    """A global name links the global row; nothing private is created."""
    onion = make_ingredient("onion")
    url = f"/recipes/{group.recipe.pk}/groups/{group.pk}/ingredients/create/"
    auth_client.post(url, {"ingredient_name": "Onion"})
    assert IngredientInRecipe.objects.get().ingredient == onion
    assert Ingredient.objects.count() == 1


@pytest.mark.django_db
def test_editor_datalist_hides_other_users_private_names(auth_client, group, private, other_user):
    """The add form's suggestions skip another user's private rows."""
    private("secret-sauce", owner=other_user)
    url = f"/recipes/{group.recipe.pk}/groups/{group.pk}/ingredients/add/"
    html = auth_client.post(url).content.decode()
    assert "secret-sauce" not in html


# --- Clean-up tool services ---------------------------------------------------


@pytest.mark.django_db
def test_a_private_replacement_cannot_reach_another_users_recipe(
    private, make_ingredient, make_recipe, add_ingredient, user, other_user
):
    """Repointing someone else's recipe onto my private row would leak it."""
    onion = make_ingredient("onion")
    theirs = make_recipe(owner=other_user, name="Theirs")
    add_ingredient(recipe=theirs, ingredient=onion)
    mine = private("my onion", owner=user)
    with pytest.raises(IngredientScopeError):
        delete_ingredients(ingredient_ids=[onion.pk], replacement_id=mine.pk)
    with pytest.raises(IngredientScopeError):
        merge_ingredients(survivor_id=mine.pk, victim_ids=[onion.pk, mine.pk])
    assert IngredientInRecipe.objects.get().ingredient == onion


@pytest.mark.django_db
def test_a_private_replacement_may_serve_its_owners_recipes(
    private, make_recipe, add_ingredient, user
):
    """Merging two of my own private rows is fine."""
    a = private("yuzu", owner=user)
    b = private("yuzu juice", owner=user)
    recipe = make_recipe(owner=user, name="Mine")
    add_ingredient(recipe=recipe, ingredient=b)
    merge_ingredients(survivor_id=a.pk, victim_ids=[a.pk, b.pk])
    assert IngredientInRecipe.objects.get().ingredient == a


@pytest.mark.django_db
def test_promote_makes_a_private_row_global(private, user):
    """Promoting clears the owner."""
    yuzu = private("yuzu", owner=user)
    assert promote_ingredients([yuzu.pk]) == [yuzu.pk]
    yuzu.refresh_from_db()
    assert yuzu.owner is None


@pytest.mark.django_db
def test_promote_folds_other_users_same_named_rows_in(
    private, make_recipe, add_ingredient, user, other_user
):
    """Everyone's `yuzu` becomes the one global `yuzu`, recipes and all."""
    mine = private("yuzu", owner=user)
    theirs = private("Yuzu", owner=other_user)
    their_recipe = make_recipe(owner=other_user, name="Theirs")
    add_ingredient(recipe=their_recipe, ingredient=theirs)
    promote_ingredients([mine.pk])
    assert list(Ingredient.objects.all()) == [mine]
    assert IngredientInRecipe.objects.get().ingredient == mine


@pytest.mark.django_db
def test_promote_onto_an_existing_global_merges_into_it(
    private, make_ingredient, make_recipe, add_ingredient, user
):
    """If staff already made `yuzu` global, the private row merges into it."""
    glob = make_ingredient("yuzu")
    mine = private("YUZU", owner=user)
    recipe = make_recipe(owner=user, name="Mine")
    add_ingredient(recipe=recipe, ingredient=mine)
    assert promote_ingredients([mine.pk]) == [glob.pk]
    assert list(Ingredient.objects.all()) == [glob]
    assert IngredientInRecipe.objects.get().ingredient == glob


@pytest.mark.django_db
def test_promote_leaves_global_rows_alone(make_ingredient):
    """A global row in the selection is already promoted."""
    onion = make_ingredient("onion")
    assert promote_ingredients([onion.pk]) == [onion.pk]
    onion.refresh_from_db()
    assert onion.owner is None


@pytest.mark.django_db
def test_search_can_narrow_to_private_rows(make_ingredient, private, user):
    """Staff find promotion candidates with the private-only filter."""
    make_ingredient("onion")
    yuzu = private("yuzu", owner=user)
    assert list(search_ingredients("", private_only=True)) == [yuzu]


# --- Clean-up tool edit form ---------------------------------------------------


@pytest.mark.django_db
def test_a_private_row_cannot_be_renamed_onto_a_global_name(private, make_ingredient, user):
    """The global row would shadow it; that is a merge."""
    make_ingredient("onion")
    mine = private("onoin", owner=user)
    form = IngredientForm(data={"ingredient_name": "Onion"}, instance=mine)
    assert not form.is_valid()


@pytest.mark.django_db
def test_a_private_row_may_share_a_name_with_another_users_row(private, user, other_user):
    """Private names only clash within one owner."""
    private("yuzu", owner=other_user)
    mine = private("yuzzu", owner=user)
    form = IngredientForm(data={"ingredient_name": "yuzu"}, instance=mine)
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_a_global_row_may_take_a_name_a_private_row_has(private, make_ingredient, user):
    """Global wins at resolution, so the private row is just shadowed."""
    private("yuzu", owner=user)
    glob = make_ingredient("yuzzu")
    form = IngredientForm(data={"ingredient_name": "yuzu"}, instance=glob)
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_a_global_rename_still_clashes_with_another_global(make_ingredient):
    """The global list stays unique."""
    make_ingredient("onion")
    other = make_ingredient("onoin")
    form = IngredientForm(data={"ingredient_name": "ONION"}, instance=other)
    assert not form.is_valid()


# --- Clean-up tool views -------------------------------------------------------

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


@pytest.mark.django_db
def test_column_two_labels_private_rows_with_their_owner(staff_client, private, other_user):
    """Staff can tell a private row from a global one, and whose it is."""
    private("yuzu", owner=other_user)
    html = staff_client.get(MANAGE + "search/").content.decode()
    assert "someone-else" in html


@pytest.mark.django_db
def test_private_filter_narrows_column_two(staff_client, make_ingredient, private, other_user):
    """`private=1` lists private rows only."""
    make_ingredient("onion")
    private("yuzu", owner=other_user)
    html = staff_client.get(MANAGE + "search/", {"private": "1"}).content.decode()
    assert "yuzu" in html
    assert "onion" not in html


@pytest.mark.django_db
def test_promote_get_shows_a_confirmation(staff_client, private, user, other_user):
    """GET explains what Promote will do, including other users' copies."""
    mine = private("yuzu", owner=user)
    private("Yuzu", owner=other_user)
    response = staff_client.get(MANAGE + "promote/", {"ingredient_ids": [mine.pk]})
    html = response.content.decode()
    assert response.status_code == 200
    assert "yuzu" in html
    assert "someone-else" in html


@pytest.mark.django_db
def test_promote_post_makes_the_row_global(staff_client, private, other_user):
    """POST promotes and keeps the promoted row ticked."""
    yuzu = private("yuzu", owner=other_user)
    response = staff_client.post(MANAGE + "promote/", {"ingredient_ids": [yuzu.pk]})
    assert response.status_code == 200
    yuzu.refresh_from_db()
    assert yuzu.owner is None
    assert f'value="{yuzu.pk}"' in response.content.decode()


@pytest.mark.django_db
def test_promote_needs_a_selection(staff_client):
    """Nothing selected answers 422."""
    assert staff_client.post(MANAGE + "promote/").status_code == 422


@pytest.mark.django_db
def test_merging_onto_a_private_row_used_elsewhere_answers_422(
    staff_client, private, make_ingredient, make_recipe, add_ingredient, user, other_user
):
    """The merge view reports the scope error instead of a 500."""
    onion = make_ingredient("onion")
    add_ingredient(recipe=make_recipe(owner=other_user, name="Theirs"), ingredient=onion)
    mine = private("my onion", owner=user)
    response = staff_client.post(
        MANAGE + "merge/", {"ingredient_ids": [onion.pk, mine.pk], "survivor_id": mine.pk}
    )
    assert response.status_code == 422
    assert "promote it first" in response.content.decode()
    assert Ingredient.objects.filter(pk=onion.pk).exists()
