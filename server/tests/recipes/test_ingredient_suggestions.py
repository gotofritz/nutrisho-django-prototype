"""Ingredient-name autocomplete for the recipe editor (#80).

The editor used to ship every visible ingredient name as a `<datalist>` with each
edit form. Now the datalist starts empty and the name inputs fetch the top
matches for what has been typed so far.
"""

import pytest

from recipes.models import Ingredient
from recipes.services.name_resolution import SUGGESTION_LIMIT, suggest_ingredient_names

SUGGEST_URL = "/recipes/ingredients/suggest/"


@pytest.fixture
def private(db):
    """Make a row private to `owner`."""

    def _make(name: str, *, owner) -> Ingredient:
        return Ingredient.objects.create(ingredient_name=name, owner=owner)

    return _make


# --- Service -------------------------------------------------------------------


@pytest.mark.django_db
def test_prefix_matches_come_before_matches_inside_the_name(make_ingredient, user):
    """`on` lists `onion` before `lemon`, each half sorted ignoring case."""
    for name in ("spring onion", "Onion", "lemon", "onigiri", "garlic"):
        make_ingredient(name)
    assert suggest_ingredient_names("on", owner=user) == [
        "onigiri",
        "Onion",
        "lemon",
        "spring onion",
    ]


@pytest.mark.django_db
def test_matching_ignores_case_and_surrounding_space(make_ingredient, user):
    """`  ONI ` still finds `onion`."""
    make_ingredient("onion")
    assert suggest_ingredient_names("  ONI ", owner=user) == ["onion"]


@pytest.mark.django_db
def test_blank_text_suggests_nothing(make_ingredient, user):
    """Nothing typed is no query, not the whole table."""
    make_ingredient("onion")
    assert suggest_ingredient_names("   ", owner=user) == []


@pytest.mark.django_db
def test_suggestions_stop_at_the_limit(user):
    """Only the top `SUGGESTION_LIMIT` names come back, prefix matches first."""
    Ingredient.objects.bulk_create(
        [Ingredient(ingredient_name=f"salt {n:02}") for n in range(SUGGESTION_LIMIT + 5)]
        + [Ingredient(ingredient_name="sea salt")]
    )
    names = suggest_ingredient_names("salt", owner=user)
    assert len(names) == SUGGESTION_LIMIT
    assert names[0] == "salt 00"
    assert "sea salt" not in names


@pytest.mark.django_db
def test_contains_matches_fill_up_to_the_limit(make_ingredient, user):
    """A short prefix list leaves room for names that merely contain the text."""
    make_ingredient("rice")
    make_ingredient("wild rice")
    assert suggest_ingredient_names("rice", owner=user) == ["rice", "wild rice"]


@pytest.mark.django_db
def test_like_wildcards_are_matched_literally(make_ingredient, user):
    """`%` and `_` are characters to find, not LIKE patterns."""
    make_ingredient("50% cocoa")
    make_ingredient("500g flour")
    make_ingredient("a_b")
    make_ingredient("axb")
    assert suggest_ingredient_names("50%", owner=user) == ["50% cocoa"]
    assert suggest_ingredient_names("a_", owner=user) == ["a_b"]


@pytest.mark.django_db
def test_suggestions_are_global_plus_own(make_ingredient, private, user, other_user):
    """Another user's private names never leak into the suggestions."""
    make_ingredient("yuzu kosho")
    private("yuzu", owner=user)
    private("yuzu juice", owner=other_user)
    assert suggest_ingredient_names("yuzu", owner=user) == ["yuzu", "yuzu kosho"]


@pytest.mark.django_db
def test_a_private_twin_of_a_global_name_is_suggested_once(make_ingredient, private, user):
    """The global spelling wins, as it does when the name is resolved."""
    make_ingredient("Yuzu")
    private("yuzu", owner=user)
    assert suggest_ingredient_names("yu", owner=user) == ["Yuzu"]


# --- Endpoint ------------------------------------------------------------------


@pytest.mark.django_db
def test_endpoint_returns_options_for_the_typed_ingredient(auth_client, make_ingredient):
    """The ingredient input sends its own name, `ingredient_name`."""
    make_ingredient("onion")
    make_ingredient("garlic")
    response = auth_client.get(SUGGEST_URL, {"ingredient_name": "oni"})
    assert response.status_code == 200
    content = response.content.decode()
    assert '<option value="onion">' in content
    assert "garlic" not in content


@pytest.mark.django_db
def test_endpoint_reads_the_substitute_input_too(auth_client, make_ingredient):
    """The substitute input shares the datalist and sends `substitute_name`."""
    make_ingredient("shallot")
    response = auth_client.get(SUGGEST_URL, {"substitute_name": "shal"})
    assert '<option value="shallot">' in response.content.decode()


@pytest.mark.django_db
def test_endpoint_escapes_names(auth_client, make_ingredient):
    """A stored name is text, never markup."""
    make_ingredient('salt "flakes"')
    response = auth_client.get(SUGGEST_URL, {"ingredient_name": "salt"})
    assert '<option value="salt &quot;flakes&quot;">' in response.content.decode()


@pytest.mark.django_db
def test_endpoint_scopes_to_the_signed_in_user(auth_client, private, other_user):
    """Another user's private row stays invisible."""
    private("secret sauce", owner=other_user)
    response = auth_client.get(SUGGEST_URL, {"ingredient_name": "secret"})
    assert "secret sauce" not in response.content.decode()


@pytest.mark.django_db
def test_endpoint_with_nothing_typed_is_empty(auth_client, make_ingredient):
    """No text, no options."""
    make_ingredient("onion")
    response = auth_client.get(SUGGEST_URL)
    assert response.status_code == 200
    assert "<option" not in response.content.decode()


@pytest.mark.django_db
def test_endpoint_refuses_post(auth_client):
    """It only reads."""
    assert auth_client.post(SUGGEST_URL).status_code == 405


# --- Editor form -----------------------------------------------------------------


@pytest.fixture
def edit_url(make_recipe, add_ingredient, make_ingredient, user) -> str:
    """The edit form of an `onion` row in the default user's recipe."""
    recipe = make_recipe(owner=user, name="Soup")
    iir = add_ingredient(recipe=recipe, ingredient=make_ingredient("onion"))
    return f"/recipes/{recipe.pk}/ingredients/{iir.pk}/edit/"


@pytest.mark.django_db
def test_edit_form_no_longer_ships_the_ingredient_table(auth_client, edit_url, make_ingredient):
    """The datalist starts empty: an unrelated name is not in the form."""
    make_ingredient("garlic")
    content = auth_client.get(edit_url).content.decode()
    assert '<datalist id="ingredients-datalist">' in content
    assert "garlic" not in content


@pytest.mark.django_db
def test_both_name_inputs_fetch_suggestions(auth_client, edit_url):
    """Ingredient and substitute ask the endpoint as the user types."""
    content = auth_client.get(edit_url).content.decode()
    for name in ("ingredient_name", "substitute_name"):
        start = content.index(f'name="{name}"')
        tag = content[content.rindex("<input", 0, start) : content.index(">", start)]
        assert f'hx-get="{SUGGEST_URL}"' in tag
        assert 'hx-trigger="input changed delay:200ms"' in tag
        assert 'hx-target="#ingredients-datalist"' in tag
        assert 'list="ingredients-datalist"' in tag
