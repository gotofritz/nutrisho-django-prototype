"""Global and private tags (plan 011, PR 3).

`Tag.owner` is NULL for a global tag, curated by staff in Django admin, and a
user for a tag private to that user. Tags are edited on the recipe's metadata
form as comma-separated names; an unknown name becomes a private tag.
"""

import pytest
from django.db import IntegrityError, transaction

from recipes.forms.field_forms import RecipeMetadataForm
from recipes.models import Recipe, Tag
from recipes.services.name_resolution import find_tag, resolve_tag


def _tag_names(recipe: Recipe) -> list[str]:
    return sorted(recipe.tag.values_list("tag", flat=True))  # ty: ignore[unresolved-attribute]  # reverse M2M


# --- Model -------------------------------------------------------------------


@pytest.mark.django_db
def test_two_users_may_each_have_a_private_tag_with_the_same_name(user, other_user):
    """Private names only clash within one owner."""
    Tag.objects.create(tag="quick", owner=user)
    Tag.objects.create(tag="Quick", owner=other_user)
    assert Tag.objects.count() == 2


@pytest.mark.django_db
def test_one_user_cannot_have_two_tags_differing_by_case(user):
    """Within one owner, tag names are unique ignoring case."""
    Tag.objects.create(tag="quick", owner=user)
    with pytest.raises(IntegrityError), transaction.atomic():
        Tag.objects.create(tag="QUICK", owner=user)


@pytest.mark.django_db
def test_two_global_tags_cannot_differ_by_case():
    """The global list is unique ignoring case."""
    Tag.objects.create(tag="vegan")
    with pytest.raises(IntegrityError), transaction.atomic():
        Tag.objects.create(tag="Vegan")


# --- Resolution --------------------------------------------------------------


@pytest.mark.django_db
def test_resolve_tag_prefers_global_then_own_and_creates_private(user, other_user):
    """Same order as ingredients: global, own, else a new private tag."""
    vegan = Tag.objects.create(tag="vegan")
    mine = Tag.objects.create(tag="weeknight", owner=user)
    Tag.objects.create(tag="secret", owner=other_user)
    assert resolve_tag("Vegan", owner=user) == vegan
    assert resolve_tag("WEEKNIGHT", owner=user) == mine
    created = resolve_tag("secret", owner=user)
    assert created.owner == user
    assert Tag.objects.filter(tag="secret").count() == 2


@pytest.mark.django_db
def test_find_tag_never_sees_another_users_tag(user, other_user):
    """`find_tag` looks up only, and only in global plus own."""
    Tag.objects.create(tag="secret", owner=other_user)
    assert find_tag("secret", owner=user) is None


# --- Metadata form -------------------------------------------------------------


def _data(**overrides: str) -> dict[str, str]:
    data = {
        "recipe_name": "Dal",
        "short_description": "",
        "servings": "4",
        "source_instance": "",
        "cuisine_name": "",
        "tags": "",
    }
    return data | overrides


@pytest.mark.django_db
def test_new_recipe_gets_its_tags(user):
    """Comma-separated names become the recipe's tags."""
    form = RecipeMetadataForm(data=_data(tags="quick, Vegan ,, quick"), owner=user)
    assert form.is_valid(), form.errors
    form.instance.owner = user
    recipe = form.save()
    assert _tag_names(recipe) == ["Vegan", "quick"]
    assert set(Tag.objects.values_list("owner", flat=True)) == {user.pk}


@pytest.mark.django_db
def test_form_shows_existing_tags(user):
    """The field starts with the recipe's tags, comma-separated."""
    recipe = Recipe.objects.create(recipe_name="Dal", owner=user)
    recipe.tag.add(Tag.objects.create(tag="vegan"), Tag.objects.create(tag="quick", owner=user))
    form = RecipeMetadataForm(instance=recipe, owner=user)
    assert form["tags"].value() == "quick, vegan"


@pytest.mark.django_db
def test_form_rejects_an_overlong_tag(user):
    """A tag longer than the column is a form error, not a 500."""
    form = RecipeMetadataForm(data=_data(tags="x" * 65), owner=user)
    assert not form.is_valid()
    assert "tags" in form.errors


@pytest.mark.django_db
def test_metadata_edit_replaces_the_tags(auth_client, user):
    """Saving the metadata panel sets exactly the typed tags."""
    recipe = Recipe.objects.create(recipe_name="Dal", owner=user, servings=4)
    recipe.tag.add(Tag.objects.create(tag="old", owner=user))
    vegan = Tag.objects.create(tag="vegan")
    response = auth_client.post(
        f"/recipes/{recipe.pk}/metadata/", _data(tags="Vegan, weeknight"), HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 200
    assert _tag_names(recipe) == ["vegan", "weeknight"]
    assert vegan in recipe.tag.all()


@pytest.mark.django_db
def test_metadata_edit_can_clear_the_tags(auth_client, user):
    """An empty field removes every tag."""
    recipe = Recipe.objects.create(recipe_name="Dal", owner=user, servings=4)
    recipe.tag.add(Tag.objects.create(tag="old", owner=user))
    auth_client.post(f"/recipes/{recipe.pk}/metadata/", _data(), HTTP_HX_REQUEST="true")
    assert _tag_names(recipe) == []


@pytest.mark.django_db
def test_new_recipe_view_saves_tags(auth_client, user):
    """The new-recipe page takes tags too."""
    auth_client.post("/recipes/new/", _data(recipe_name="Soup", tags="quick"))
    recipe = Recipe.objects.get(recipe_name="Soup")
    assert _tag_names(recipe) == ["quick"]


# --- Migration 0019 ------------------------------------------------------------


@pytest.fixture
def without_tag_ci_constraints(db):
    """Drop the new indexes so pre-0019 case clashes can exist."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX tag_ci_unique")
        cursor.execute("DROP INDEX tag_ci_unique_per_owner")


@pytest.mark.django_db
def test_migration_merges_case_duplicate_tags_into_the_most_used(without_tag_ci_constraints, user):
    """Recipes move to the most-used spelling and the other rows go."""
    import importlib

    from django.apps import apps

    lower = Tag.objects.create(tag="vegan")
    upper = Tag.objects.create(tag="Vegan")
    a = Recipe.objects.create(recipe_name="A", owner=user)
    b = Recipe.objects.create(recipe_name="B", owner=user)
    lower.recipe.add(a)
    upper.recipe.add(a, b)
    module = importlib.import_module("recipes.migrations.0019_tag_owner")
    module.merge_case_duplicate_tags(apps, None)
    assert list(Tag.objects.all()) == [upper]
    assert sorted(upper.recipe.values_list("recipe_name", flat=True)) == ["A", "B"]
