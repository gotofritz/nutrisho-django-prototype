"""Tests for recipes models."""

import pytest

from recipes.models import (
    Cuisine,
    Ingredient,
    IngredientGroup,
    IngredientInRecipe,
    Recipe,
    Source,
    Step,
    Tag,
)


@pytest.mark.django_db
def test_recipe_creation(user):
    recipe = Recipe.objects.create(recipe_name="Test Recipe", owner=user)
    assert recipe.recipe_name == "Test Recipe"
    assert recipe.pk is not None


@pytest.mark.django_db
def test_recipe_servings_can_be_null(user):
    """servings=None is valid for legacy rows where count is unknown."""
    r = Recipe.objects.create(recipe_name="Unknown Serves", owner=user, servings=None)
    r.refresh_from_db()
    assert r.servings is None


@pytest.mark.django_db
def test_recipe_natural_key(user):
    recipe = Recipe.objects.create(recipe_name="Pasta Carbonara", owner=user)
    assert recipe.natural_key() == (user.username, "Pasta Carbonara")


@pytest.mark.django_db
def test_recipe_get_by_natural_key(user):
    Recipe.objects.create(recipe_name="Pasta Carbonara", owner=user)
    fetched = Recipe.objects.get_by_natural_key(user.username, "Pasta Carbonara")
    assert fetched.recipe_name == "Pasta Carbonara"
    assert fetched.owner == user


@pytest.mark.django_db
def test_recipe_natural_key_two_owners_same_name(user, db):
    """Two owners with same recipe name must have distinct natural keys."""
    from django.contrib.auth.models import User

    bob = User.objects.create_user(username="bob_nk", password="x")
    Recipe.objects.create(recipe_name="Soup", owner=user)
    Recipe.objects.create(recipe_name="Soup", owner=bob)
    key_a = Recipe.objects.get(owner=user, recipe_name="Soup").natural_key()
    key_b = Recipe.objects.get(owner=bob, recipe_name="Soup").natural_key()
    assert key_a != key_b


@pytest.mark.django_db
def test_recipe_absolute_url(user):
    recipe = Recipe.objects.create(recipe_name="Soup", owner=user)
    assert recipe.get_absolute_url() == f"/recipes/{recipe.pk}/"


@pytest.mark.django_db
def test_cuisine_natural_key():
    c = Cuisine.objects.create(cuisine="Italian")
    assert c.natural_key() == "Italian"


@pytest.mark.django_db
def test_source_natural_key():
    s = Source.objects.create(short_name="Moro", source="ISBN-123")
    assert s.natural_key() == "Moro"


@pytest.mark.django_db
def test_tag_natural_key(user):
    recipe = Recipe.objects.create(recipe_name="Tagged", owner=user)
    t = Tag.objects.create(tag="vegan")
    t.recipe.add(recipe)
    assert t.natural_key() == "vegan"


@pytest.mark.django_db
def test_ingredient_natural_key():
    ing = Ingredient.objects.create(ingredient_name="salt")
    assert ing.natural_key() == "salt"


@pytest.mark.django_db
def test_ingredient_group_natural_key(user):
    recipe = Recipe.objects.create(recipe_name="R", owner=user)
    g = IngredientGroup.objects.create(recipe=recipe, group_name="Main", index_in_sequence=0)
    assert g.natural_key() == "Main"


@pytest.mark.django_db
def test_step_natural_key(user):
    recipe = Recipe.objects.create(recipe_name="R", owner=user)
    step = Step.objects.create(recipe=recipe, step_text="Chop", index_in_sequence=0)
    assert step.natural_key() == (0, "Chop")


@pytest.mark.django_db
def test_ingredient_in_recipe_natural_key(user):
    recipe = Recipe.objects.create(recipe_name="R", owner=user)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="G", index_in_sequence=0)
    ing = Ingredient.objects.create(ingredient_name="onion")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=0, quantity=2
    )
    key = iir.natural_key()
    assert key[3] == "onion"


@pytest.mark.django_db
def test_recipe_servings_default(user):
    """New Recipe has servings=None by default (unknown serving count)."""
    recipe = Recipe.objects.create(recipe_name="Default Servings Recipe", owner=user)
    assert recipe.servings is None


@pytest.mark.django_db
def test_recipe_servings_explicit(user):
    """Recipe can be created with an explicit servings value."""
    recipe = Recipe.objects.create(recipe_name="Feeds a Crowd", owner=user, servings=6)
    assert recipe.servings == 6


@pytest.mark.django_db
def test_ingredient_group_duplicate_index_rejected(user):
    """Two IngredientGroups with the same recipe+index_in_sequence raise IntegrityError."""
    import django.db

    recipe = Recipe.objects.create(recipe_name="Dup Group Recipe", owner=user)
    IngredientGroup.objects.create(recipe=recipe, group_name="A", index_in_sequence=1)
    with pytest.raises(django.db.IntegrityError):
        IngredientGroup.objects.create(recipe=recipe, group_name="B", index_in_sequence=1)


@pytest.mark.django_db
def test_ingredient_in_recipe_duplicate_index_rejected(user):
    """Two IngredientInRecipe rows with same group+index_in_sequence raise IntegrityError."""
    import django.db

    recipe = Recipe.objects.create(recipe_name="Dup IIR Recipe", owner=user)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="", index_in_sequence=1)
    ing_a, _ = Ingredient.objects.get_or_create(ingredient_name="salt")
    ing_b, _ = Ingredient.objects.get_or_create(ingredient_name="pepper")
    IngredientInRecipe.objects.create(ingredient=ing_a, ingredient_group=group, index_in_sequence=1)
    with pytest.raises(django.db.IntegrityError):
        IngredientInRecipe.objects.create(
            ingredient=ing_b, ingredient_group=group, index_in_sequence=1
        )


@pytest.mark.django_db
def test_recipe_save_sanitizes_yaml_filename(user):
    """Recipe.save() must sanitize yaml_filename so unsanitized values never reach the DB."""
    recipe = Recipe.objects.create(
        recipe_name="Sanitize Test", owner=user, yaml_filename="foo!bar.yml"
    )
    recipe.refresh_from_db()
    assert recipe.yaml_filename == "foobar.yml"


@pytest.mark.django_db
def test_recipe_save_preserves_already_sanitized_filename(user):
    """Recipe.save() must not alter an already-sanitized yaml_filename."""
    recipe = Recipe.objects.create(
        recipe_name="Preserve Test", owner=user, yaml_filename="my_recipe.yml"
    )
    recipe.refresh_from_db()
    assert recipe.yaml_filename == "my_recipe.yml"


@pytest.mark.django_db
def test_recipe_save_preserves_blank_yaml_filename(user):
    """Empty yaml_filename stays empty — no fallback substitution on save."""
    recipe = Recipe.objects.create(recipe_name="No File Test", owner=user, yaml_filename="")
    recipe.refresh_from_db()
    assert recipe.yaml_filename == ""


@pytest.mark.django_db
def test_ingredient_in_recipe_protects_ingredient(user):
    """Deleting an Ingredient still referenced by a recipe must raise ProtectedError."""
    from django.db.models import ProtectedError

    recipe = Recipe.objects.create(recipe_name="Protect Test", owner=user)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="Main", index_in_sequence=0)
    ing = Ingredient.objects.create(ingredient_name="protected-onion")
    IngredientInRecipe.objects.create(ingredient=ing, ingredient_group=group, index_in_sequence=0)
    with pytest.raises(ProtectedError):
        ing.delete()


@pytest.mark.django_db
def test_ingredient_in_recipe_natural_key_is_serializable(user):
    """natural_key must not contain model instances."""
    from django.db.models import Model

    recipe = Recipe.objects.create(recipe_name="NK Test", owner=user)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="Main", index_in_sequence=0)
    ing = Ingredient.objects.create(ingredient_name="nk-onion")
    iir = IngredientInRecipe.objects.create(
        ingredient=ing, ingredient_group=group, index_in_sequence=0
    )
    assert not any(isinstance(part, Model) for part in iir.natural_key())


def test_char_fields_are_not_nullable():
    """CharFields should use blank-only emptiness, never NULL (single empty state)."""
    assert Recipe._meta.get_field("short_description").null is False
    assert IngredientGroup._meta.get_field("group_name").null is False
    assert IngredientInRecipe._meta.get_field("unit").null is False
    assert IngredientInRecipe._meta.get_field("preparation").null is False
