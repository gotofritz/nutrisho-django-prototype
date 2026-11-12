"""Re-renders of a recipe's groups and rows cost the same queries at any size (#64).

Each endpoint is measured on a small and a large recipe; the count must not
grow with the number of groups, rows or steps. Every row has a unit and a
substitute, so a missing `select_related` on either shows up as growth.
"""

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step
from recipes.services.name_resolution import find_unit

SMALL = (2, 3, 3)  # groups, rows per group, steps
LARGE = (5, 8, 10)


@dataclass
class Built:
    """A recipe and its groups, each group's rows in order."""

    recipe: Recipe
    groups: list[IngredientGroup]
    rows: list[list[IngredientInRecipe]]


@pytest.fixture
def staff_client(user) -> Client:
    """The owner, made staff so the clean-up tool's preview is open to them."""
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def build(user) -> Callable[..., Built]:
    """Build a recipe of `groups` groups of `rows` rows each, and `steps` steps."""
    unit = find_unit("clove")
    assert unit is not None
    made = 0

    def _build(groups: int, rows: int, steps: int) -> Built:
        nonlocal made
        made += 1
        recipe = Recipe.objects.create(recipe_name=f"Recipe {made}", owner=user, servings=4)
        built = Built(recipe=recipe, groups=[], rows=[])
        for g in range(groups):
            group = IngredientGroup.objects.create(
                recipe=recipe, group_name=f"Group {g}", index_in_sequence=g
            )
            built.groups.append(group)
            built.rows.append(
                [
                    IngredientInRecipe.objects.create(
                        ingredient_group=group,
                        index_in_sequence=r,
                        ingredient=Ingredient.objects.create(
                            ingredient_name=f"ingredient {made}-{g}-{r}"
                        ),
                        substitute=Ingredient.objects.create(
                            ingredient_name=f"substitute {made}-{g}-{r}"
                        ),
                        unit=unit,
                        quantity=2,
                    )
                    for r in range(rows)
                ]
            )
        for s in range(steps):
            Step.objects.create(recipe=recipe, step_text=f"Step {s}", index_in_sequence=s)
        return built

    return _build


Request = tuple[str, str, dict[str, object]]


def _page(b: Built) -> Request:
    return "get", reverse("recipes:recipe", args=[b.recipe.pk]), {}


def _group_up(b: Built) -> Request:
    return "post", reverse("recipes:group_move_up", args=[b.recipe.pk, b.groups[-1].pk]), {}


def _group_down(b: Built) -> Request:
    return "post", reverse("recipes:group_move_down", args=[b.recipe.pk, b.groups[0].pk]), {}


def _ingredient_up(b: Built) -> Request:
    iir = b.rows[0][-1]
    return "post", reverse("recipes:ingredient_move_up", args=[b.recipe.pk, iir.pk]), {}


def _ingredient_down(b: Built) -> Request:
    iir = b.rows[0][0]
    return "post", reverse("recipes:ingredient_move_down", args=[b.recipe.pk, iir.pk]), {}


def _reassign(b: Built) -> Request:
    # The last row of the first group into a new group: the writes stay the same
    # at any size, since nothing is left behind to compact.
    data = {
        "ingredient_ids": [b.rows[0][-1].pk],
        "target_group": "new",
        "new_group_name": "Moved",
    }
    return "post", reverse("recipes:ingredient_reassign", args=[b.recipe.pk]), data


def _reassign_noop(b: Built) -> Request:
    data = {"ingredient_ids": [b.rows[0][0].pk], "target_group": b.groups[0].pk}
    return "post", reverse("recipes:ingredient_reassign", args=[b.recipe.pk]), data


def _preview(b: Built) -> Request:
    return "get", reverse("recipes:ingredient_manage_preview", args=[b.recipe.pk]), {}


def _queries(client: Client, request: Request) -> int:
    method, url, data = request
    with CaptureQueriesContext(connection) as ctx:
        response = getattr(client, method)(url, data, headers={"HX-Request": "true"})
    assert response.status_code == 200, response.content
    return len(ctx.captured_queries)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "make_request",
    [
        _page,
        _group_up,
        _group_down,
        _ingredient_up,
        _ingredient_down,
        _reassign,
        _reassign_noop,
        _preview,
    ],
    ids=lambda f: f.__name__.lstrip("_"),
)
def test_query_count_does_not_grow_with_recipe_size(staff_client, build, make_request):
    """The same endpoint costs the same queries on a small and a large recipe."""
    small = _queries(staff_client, make_request(build(*SMALL)))
    large = _queries(staff_client, make_request(build(*LARGE)))
    assert large == small


@pytest.mark.django_db
def test_refused_last_group_delete_does_not_grow_with_row_count(staff_client, build):
    """Deleting a recipe's only group re-renders it, at the same cost for any row count."""

    def _delete(b: Built) -> Request:
        return "post", reverse("recipes:group_delete", args=[b.recipe.pk, b.groups[0].pk]), {}

    small = _queries(staff_client, _delete(build(1, 3, 0)))
    large = _queries(staff_client, _delete(build(1, 10, 0)))
    assert large == small
