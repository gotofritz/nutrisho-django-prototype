"""The curated cuisine tree (plan 011, PR 4).

Cuisines are nodes `area.region.subregion` (`med.italy.sicily`). Migration 0021
seeds the agreed list; the editor picks from it and never creates a cuisine.
"""

import importlib

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from recipes.forms.field_forms import RecipeMetadataForm
from recipes.models import Cuisine, Recipe, Tag
from recipes.services.name_resolution import cuisine_paths, find_cuisine

SEED = importlib.import_module("recipes.migrations.0021_seed_cuisine_tree")
AREAS = {"eu", "med", "middle east", "africa", "asia", "south asia", "anglo", "latin"}


def _node(path: str) -> Cuisine:
    """The seeded node at `path`; fails the test if it is missing."""
    node = find_cuisine(path)
    assert node is not None, path
    return node


# --- Seeded list ---------------------------------------------------------------


@pytest.mark.django_db
def test_the_areas_are_seeded():
    """The top level is the agreed set of areas."""
    roots = set(Cuisine.objects.filter(parent=None).values_list("cuisine", flat=True))
    assert roots == AREAS


@pytest.mark.django_db
def test_a_subregion_has_its_full_path():
    """`sicily` sits under `med.italy`."""
    sicily = find_cuisine("med.italy.sicily")
    assert sicily is not None
    assert sicily.path == "med.italy.sicily"
    assert str(sicily) == "med.italy.sicily"


@pytest.mark.django_db
def test_nothing_is_seeded_deeper_than_three_levels():
    """area.region.subregion is the limit."""
    assert not Cuisine.objects.filter(parent__parent__parent__isnull=False).exists()


@pytest.mark.django_db
def test_style_tags_are_seeded_as_global_tags():
    """`fusion` and `modern` are styles, kept as global tags rather than cuisines."""
    assert set(Tag.objects.filter(owner=None).values_list("tag", flat=True)) >= {"fusion", "modern"}
    assert not Cuisine.objects.filter(cuisine__in=["fusion", "modern"]).exists()


def test_every_alias_points_at_a_seeded_path():
    """A typo in `ALIASES` would crash the migration on real data."""
    paths = set()
    for area, regions in SEED.TREE.items():
        paths.add(area)
        for region, subregions in regions.items():
            paths.add(f"{area}.{region}")
            paths.update(f"{area}.{region}.{sub}" for sub in subregions)
    assert set(SEED.ALIASES.values()) <= paths


# --- Model ---------------------------------------------------------------------


@pytest.mark.django_db
def test_siblings_cannot_share_a_name_ignoring_case():
    """No two `sicily` under `med.italy`."""
    italy = find_cuisine("med.italy")
    with pytest.raises(IntegrityError), transaction.atomic():
        Cuisine.objects.create(cuisine="Sicily", parent=italy)


@pytest.mark.django_db
def test_areas_cannot_share_a_name_ignoring_case():
    """No second `MED` area."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Cuisine.objects.create(cuisine="MED")


@pytest.mark.django_db
def test_the_same_name_may_sit_under_different_parents():
    """`north` is a region of thailand and of vietnam."""
    assert find_cuisine("asia.thailand.north") != find_cuisine("asia.vietnam.north")


@pytest.mark.django_db
def test_a_fourth_level_is_rejected():
    """Validation stops `med.italy.sicily.palermo`."""
    palermo = Cuisine(cuisine="palermo", parent=find_cuisine("med.italy.sicily"))
    with pytest.raises(ValidationError):
        palermo.full_clean()


@pytest.mark.django_db
def test_moving_a_region_with_subregions_under_another_region_is_rejected():
    """Its subregions would end up four deep."""
    italy = _node("med.italy")
    italy.parent = _node("med.spain")  # ty: ignore[invalid-assignment]  # FK descriptor
    with pytest.raises(ValidationError):
        italy.full_clean()


@pytest.mark.django_db
def test_a_node_cannot_sit_inside_itself():
    """Loops are rejected."""
    med = _node("med")
    med.parent = _node("med.italy")  # ty: ignore[invalid-assignment]  # FK descriptor
    with pytest.raises(ValidationError):
        med.full_clean()


@pytest.mark.django_db
def test_a_name_cannot_contain_the_path_separator():
    """A dot would make the path ambiguous."""
    with pytest.raises(ValidationError):
        Cuisine(cuisine="st. lucia", parent=find_cuisine("latin.caribbean")).full_clean()


@pytest.mark.django_db
def test_a_valid_new_node_passes_validation():
    """Staff can add a region, e.g. anglo.canada.quebec."""
    Cuisine(cuisine="quebec", parent=find_cuisine("anglo.canada")).full_clean()


# --- Lookup --------------------------------------------------------------------


@pytest.mark.django_db
def test_find_cuisine_by_path_ignores_case_and_spaces():
    """`MED . Italy` is `med.italy`."""
    assert find_cuisine(" MED . Italy ") == find_cuisine("med.italy")


@pytest.mark.django_db
def test_find_cuisine_accepts_an_unambiguous_bare_name():
    """`sicily` alone is enough; `north` is not."""
    assert find_cuisine("Sicily") == find_cuisine("med.italy.sicily")
    assert find_cuisine("north") is None


@pytest.mark.django_db
def test_find_cuisine_never_creates():
    """Unknown names and paths find nothing and write nothing."""
    before = Cuisine.objects.count()
    assert find_cuisine("klingon") is None
    assert find_cuisine("med.klingon") is None
    assert find_cuisine("med..italy") is None
    assert Cuisine.objects.count() == before


@pytest.mark.django_db
def test_cuisine_paths_lists_every_node_sorted():
    """The datalist offers every path, alphabetically."""
    paths = cuisine_paths()
    assert "med.italy.sicily" in paths
    assert "middle east" in paths
    assert paths == sorted(paths, key=str.lower)
    assert len(paths) == Cuisine.objects.count()


# --- Editor --------------------------------------------------------------------


def _data(**overrides: str) -> dict[str, str]:
    return {"recipe_name": "Caponata", "servings": "4", "cuisine_name": ""} | overrides


@pytest.mark.django_db
def test_picking_a_path_sets_the_cuisine(auth_client, user):
    """The new-recipe page stores the picked node."""
    auth_client.post("/recipes/new/", _data(cuisine_name="med.italy.sicily"))
    assert Recipe.objects.get().cuisine == find_cuisine("med.italy.sicily")


@pytest.mark.django_db
def test_an_unknown_cuisine_is_a_form_error_and_creates_nothing(auth_client, user):
    """Users pick from the list; only staff add to it."""
    before = Cuisine.objects.count()
    response = auth_client.post("/recipes/new/", _data(cuisine_name="klingon"))
    assert response.status_code == 200
    assert "Pick a cuisine from the list" in response.content.decode()
    assert not Recipe.objects.exists()
    assert Cuisine.objects.count() == before


@pytest.mark.django_db
def test_the_form_shows_the_cuisine_as_a_path(user):
    """Editing shows `med.italy.sicily`, not just `sicily`."""
    recipe = Recipe.objects.create(
        recipe_name="Caponata", owner=user, cuisine=find_cuisine("med.italy.sicily")
    )
    form = RecipeMetadataForm(instance=recipe, owner=user)
    assert form["cuisine_name"].value() == "med.italy.sicily"


@pytest.mark.django_db
def test_the_datalist_offers_paths(auth_client):
    """The new-recipe page suggests full paths."""
    html = auth_client.get("/recipes/new/").content.decode()
    assert '<option value="med.italy.sicily">' in html


@pytest.mark.django_db
def test_metadata_edit_can_clear_the_cuisine(auth_client, user):
    """A blank field removes the cuisine."""
    recipe = Recipe.objects.create(
        recipe_name="Caponata", owner=user, servings=4, cuisine=find_cuisine("med.italy")
    )
    auth_client.post(f"/recipes/{recipe.pk}/metadata/", _data())
    recipe.refresh_from_db()
    assert recipe.cuisine is None


# --- Migration 0021: old flat cuisines -------------------------------------------


def _map(legacy_ids: list[int]) -> None:
    from django.apps import apps

    nodes = {c.path: c for c in Cuisine.objects.exclude(pk__in=legacy_ids)}
    SEED.map_legacy_cuisines(
        cuisine_model=apps.get_model("recipes", "Cuisine"),
        recipe_model=apps.get_model("recipes", "Recipe"),
        tag_model=apps.get_model("recipes", "Tag"),
        legacy_ids=legacy_ids,
        nodes=nodes,
    )


@pytest.fixture
def legacy(db):
    """An old flat cuisine: a top-level row with a typed name.

    The area constraint forbids a second `Italian`-like row only per name, so
    these coexist with the seeded areas.
    """

    def _make(name: str) -> Cuisine:
        return Cuisine.objects.create(cuisine=name)

    return _make


@pytest.mark.django_db
def test_an_adjective_moves_onto_its_node(legacy, user):
    """`Italian` recipes move to `med.italy` and the old row goes."""
    old = legacy("Italian")
    recipe = Recipe.objects.create(recipe_name="Pasta", owner=user, cuisine=old)
    _map([old.pk])
    recipe.refresh_from_db()
    assert recipe.cuisine == find_cuisine("med.italy")
    assert not Cuisine.objects.filter(pk=old.pk).exists()


@pytest.mark.django_db
def test_a_unique_node_name_moves_onto_that_node(legacy, user):
    """`Sicily` needs no alias: only one node has that name."""
    old = legacy("Sicily ")
    recipe = Recipe.objects.create(recipe_name="Arancini", owner=user, cuisine=old)
    _map([old.pk])
    recipe.refresh_from_db()
    assert recipe.cuisine == find_cuisine("med.italy.sicily")


@pytest.mark.django_db
def test_fusion_becomes_a_tag(legacy, user):
    """A `Fusion` recipe loses the cuisine and gains the global tag."""
    old = legacy("Fusion")
    recipe = Recipe.objects.create(recipe_name="Taco pizza", owner=user, cuisine=old)
    _map([old.pk])
    recipe.refresh_from_db()
    assert recipe.cuisine is None
    assert list(recipe.tag.values_list("tag", flat=True)) == ["fusion"]
    assert not Cuisine.objects.filter(pk=old.pk).exists()


@pytest.mark.django_db
def test_an_unmatched_cuisine_is_kept(legacy, user):
    """Nothing to map onto: the row stays, so the recipe keeps its cuisine."""
    old = legacy("Klingon")
    recipe = Recipe.objects.create(recipe_name="Gagh", owner=user, cuisine=old)
    _map([old.pk])
    recipe.refresh_from_db()
    assert recipe.cuisine == old


@pytest.mark.django_db
def test_an_ambiguous_name_is_kept(legacy):
    """`North` could be thailand, vietnam or mexico: left for staff."""
    old = legacy("North")
    _map([old.pk])
    assert Cuisine.objects.filter(pk=old.pk).exists()


@pytest.mark.django_db
def test_seeding_adopts_an_existing_area_row():
    """A pre-existing top-level `Asia` becomes the `asia` area, not a clash."""
    from django.apps import apps

    model = apps.get_model("recipes", "Cuisine")
    before = Cuisine.objects.count()
    nodes = SEED.seed_tree(model)
    assert Cuisine.objects.count() == before
    assert nodes["asia"] == find_cuisine("asia")
