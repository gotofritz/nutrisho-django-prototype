"""An ingredient row's optional substitute: shown as "or X", typed in the inline form (#65)."""

import pytest

from recipes.forms.ingredient_forms import IngredientInRecipeForm
from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe

ROW = {"quantity": "80", "unit": "g", "preparation": "", "note": ""}


@pytest.fixture
def recipe(user):
    """A recipe with one empty group."""
    recipe = Recipe.objects.create(recipe_name="Pasta", owner=user)
    IngredientGroup.objects.create(recipe=recipe, group_name="Main", index_in_sequence=0)
    return recipe


@pytest.fixture
def group(recipe):
    """The recipe's only group."""
    return recipe.ingredients_group.get()


@pytest.fixture
def row(recipe, make_ingredient, add_ingredient):
    """`80 g parmesan`, with no substitute."""
    return add_ingredient(
        recipe=recipe, ingredient=make_ingredient("parmesan"), quantity=80, unit="g"
    )


def _save(auth_client, recipe, row, **fields):
    return auth_client.post(
        f"/recipes/{recipe.pk}/ingredients/{row.pk}/save/",
        {**ROW, "ingredient_name": "parmesan", **fields},
    )


@pytest.mark.django_db
def test_display_shows_the_substitute_after_the_name(auth_client, recipe, row, make_ingredient):
    """`parmesan or pecorino`."""
    row.substitute = make_ingredient("pecorino")
    row.save()
    content = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{row.pk}/").content.decode()
    assert '<span class="ingredient-substitute">or pecorino</span>' in content


@pytest.mark.django_db
def test_display_has_no_substitute_when_there_is_none(auth_client, recipe, row):
    """No stray "or"."""
    content = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{row.pk}/").content.decode()
    assert "ingredient-substitute" not in content


@pytest.mark.django_db
def test_the_substitute_is_pluralised_like_the_ingredient(
    auth_client, recipe, make_ingredient, add_ingredient
):
    """`2 onions or shallots`: same quantity, same rule."""
    row = add_ingredient(
        recipe=recipe,
        ingredient=make_ingredient("onion"),
        substitute=make_ingredient("shallot"),
        quantity=2,
    )
    content = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{row.pk}/").content.decode()
    assert "or shallots</span>" in content


@pytest.mark.django_db
def test_recipe_page_shows_substitutes(auth_client, recipe, row, make_ingredient):
    """The full page renders the row the same way."""
    row.substitute = make_ingredient("pecorino")
    row.save()
    content = auth_client.get(f"/recipes/{recipe.pk}/").content.decode()
    assert "or pecorino</span>" in content


@pytest.mark.django_db
def test_scaled_page_shows_substitutes_pluralised_at_the_scaled_quantity(
    auth_client, user, make_ingredient, add_ingredient
):
    """1 onion or shallot, doubled: 2 onions or shallots."""
    recipe = Recipe.objects.create(recipe_name="Soup", owner=user, servings=2)
    add_ingredient(
        recipe=recipe,
        ingredient=make_ingredient("onion"),
        substitute=make_ingredient("shallot"),
        quantity=1,
    )
    content = auth_client.get(f"/recipes/{recipe.pk}/?servings=4").content.decode()
    assert "or shallots</span>" in content


@pytest.mark.django_db
def test_edit_form_prefills_the_substitute(auth_client, recipe, row, make_ingredient):
    """The edit form shows the stored substitute's name."""
    row.substitute = make_ingredient("pecorino")
    row.save()
    content = auth_client.get(f"/recipes/{recipe.pk}/ingredients/{row.pk}/edit/").content.decode()
    assert 'name="substitute_name"' in content
    assert 'value="pecorino"' in content


@pytest.mark.django_db
def test_saving_sets_an_existing_substitute(auth_client, recipe, row, make_ingredient):
    """A typed name resolves to the existing ingredient."""
    pecorino = make_ingredient("pecorino")
    response = _save(auth_client, recipe, row, substitute_name="Pecorino")
    assert "<form" not in response.content.decode()
    row.refresh_from_db()
    assert row.substitute == pecorino


@pytest.mark.django_db
def test_saving_an_unknown_substitute_makes_a_private_ingredient(auth_client, user, recipe, row):
    """Resolved like `ingredient_name`: an unknown name becomes private to the owner."""
    _save(auth_client, recipe, row, substitute_name="grana padano")
    row.refresh_from_db()
    assert row.substitute is not None
    assert row.substitute.ingredient_name == "grana padano"
    assert row.substitute.owner == user


@pytest.mark.django_db
def test_saving_a_substitute_alias_stores_the_canonical(auth_client, recipe, row, make_ingredient):
    """Aliases resolve on the substitute too."""
    aubergine = make_ingredient("aubergine")
    aubergine.aliases.create(alias_name="eggplant")
    _save(auth_client, recipe, row, substitute_name="eggplant")
    row.refresh_from_db()
    assert row.substitute == aubergine


@pytest.mark.django_db
def test_saving_a_blank_substitute_clears_it(auth_client, recipe, row, make_ingredient):
    """Blank means no substitute."""
    row.substitute = make_ingredient("pecorino")
    row.save()
    _save(auth_client, recipe, row, substitute_name="  ")
    row.refresh_from_db()
    assert row.substitute is None


@pytest.mark.django_db
def test_saving_without_the_field_clears_it(auth_client, recipe, row, make_ingredient):
    """An old form that never sent the field leaves no substitute, like any blank field."""
    row.substitute = make_ingredient("pecorino")
    row.save()
    _save(auth_client, recipe, row)
    row.refresh_from_db()
    assert row.substitute is None


@pytest.mark.django_db
def test_a_substitute_cannot_be_the_ingredient_itself(auth_client, recipe, row):
    """`parmesan or parmesan` is refused, ignoring case."""
    response = _save(auth_client, recipe, row, substitute_name="Parmesan")
    content = response.content.decode()
    assert "<form" in content
    assert "substitute" in content.lower()
    row.refresh_from_db()
    assert row.substitute is None


@pytest.mark.django_db
def test_a_substitute_cannot_be_an_alias_of_the_ingredient(auth_client, recipe, make_ingredient):
    """`aubergine or eggplant` names one ingredient twice."""
    aubergine = make_ingredient("aubergine")
    aubergine.aliases.create(alias_name="eggplant")
    row = IngredientInRecipe.objects.create(
        ingredient=aubergine, ingredient_group=recipe.ingredients_group.get(), index_in_sequence=0
    )
    response = _save(
        auth_client, recipe, row, ingredient_name="aubergine", substitute_name="eggplant"
    )
    assert "<form" in response.content.decode()
    row.refresh_from_db()
    assert row.substitute is None


@pytest.mark.django_db
def test_a_refused_substitute_creates_no_ingredient(auth_client, recipe, row):
    """Validation fails before anything is written."""
    before = Ingredient.objects.count()
    _save(auth_client, recipe, row, quantity="-1", substitute_name="brand new cheese")
    assert Ingredient.objects.count() == before


@pytest.mark.django_db
def test_creating_a_row_with_a_substitute(auth_client, recipe, group, make_ingredient):
    """The new-row form takes a substitute as well."""
    pecorino = make_ingredient("pecorino")
    response = auth_client.post(
        f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/create/",
        {**ROW, "ingredient_name": "parmesan", "substitute_name": "pecorino"},
    )
    assert "or pecorino</span>" in response.content.decode()
    row = IngredientInRecipe.objects.get(ingredient_group=group)
    assert row.ingredient.ingredient_name == "parmesan"
    assert row.substitute == pecorino


@pytest.mark.django_db
def test_new_row_form_has_the_substitute_field(auth_client, recipe, group):
    """The blank form offers the field too."""
    response = auth_client.post(f"/recipes/{recipe.pk}/groups/{group.pk}/ingredients/add/")
    assert 'name="substitute_name"' in response.content.decode()


@pytest.mark.django_db
def test_form_commit_false_resolves_both_names(user, make_ingredient):
    """`resolve_names` sets the ingredient and the substitute, creating either if new."""
    form = IngredientInRecipeForm(
        owner=user,
        data={**ROW, "ingredient_name": "brand-new-cheese", "substitute_name": "another-cheese"},
    )
    assert form.is_valid()
    iir = form.save(commit=False)
    assert not Ingredient.objects.filter(ingredient_name="brand-new-cheese").exists()
    form.resolve_names(iir)
    assert iir.ingredient.ingredient_name == "brand-new-cheese"  # ty: ignore[unresolved-attribute]
    assert iir.substitute.ingredient_name == "another-cheese"  # ty: ignore[unresolved-attribute]
