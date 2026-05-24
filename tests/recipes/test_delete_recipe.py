"""Tests for delete_recipe management command."""

from io import StringIO

import pytest
from django.core.management import call_command

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step


@pytest.mark.django_db
def test_delete_recipe_reports_recipe_count_not_cascade(user):
    """Output says '1 recipe' not the total cascade row count."""
    recipe = Recipe.objects.create(recipe_name="Delete Me", owner=user)
    Step.objects.create(recipe=recipe, step_text="Step 1", index_in_sequence=1)
    Step.objects.create(recipe=recipe, step_text="Step 2", index_in_sequence=2)
    group = IngredientGroup.objects.create(recipe=recipe, group_name=None, index_in_sequence=1)
    ing = Ingredient.objects.create(ingredient_name="salt")
    IngredientInRecipe.objects.create(ingredient=ing, ingredient_group=group, index_in_sequence=1)

    out = StringIO()
    call_command("delete_recipe", ids=[recipe.pk], stdout=out)

    output = out.getvalue()
    # Must say "1 recipe" — not "5 object(s)" or any cascade total
    assert "1 recipe" in output
    assert not Recipe.objects.filter(pk=recipe.pk).exists()


@pytest.mark.django_db
def test_delete_recipe_no_match_warns(user):
    """Non-existent ID prints warning, no crash."""
    out = StringIO()
    call_command("delete_recipe", ids=[99999], stdout=out)
    assert "No recipes" in out.getvalue()


@pytest.mark.django_db
def test_delete_recipe_multiple_ids(user):
    """Multiple --id values delete all matching recipes; count is recipe count."""
    r1 = Recipe.objects.create(recipe_name="Del A", owner=user)
    r2 = Recipe.objects.create(recipe_name="Del B", owner=user)

    out = StringIO()
    call_command("delete_recipe", ids=[r1.pk, r2.pk], stdout=out)

    assert "2 recipe" in out.getvalue()
    assert not Recipe.objects.filter(pk__in=[r1.pk, r2.pk]).exists()
