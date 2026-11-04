"""Every route requires login unless it opts out, and every recipe route is owner-scoped.

The URLconf is walked rather than listed by hand, so a new route is covered the
moment it is added: it either redirects anonymous users to the login page or
appears in `PUBLIC_ROUTES`, and if it takes a `recipe_id` another user gets 404.
"""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.test import Client, RequestFactory
from django.urls import URLPattern, URLResolver, get_resolver

from recipes.models import (
    Cuisine,
    Ingredient,
    IngredientGroup,
    IngredientInRecipe,
    Recipe,
    Step,
)

# Routes an anonymous user may reach. Adding one is a deliberate choice: mark the
# view `@login_not_required` and list it here.
PUBLIC_ROUTES = frozenset(
    {
        "healthz",
        "accounts/login/",
        "accounts/password_reset/",
        "accounts/password_reset/done/",
        "accounts/reset/<uidb64>/<token>/",
        "accounts/reset/done/",
        "admin/login/",
    }
)

# Django admin guards its own views (staff login via `admin_view`) and its URLs
# are regexes, so the request walk skips it; the public-route check still covers it.
_SKIPPED_PREFIXES = ("admin/",)

_PARAM = re.compile(r"<(?:\w+:)?(\w+)>")

_MIDDLEWARE = "nutrisho.middleware.HtmxLoginRequiredMiddleware"


@dataclass(frozen=True)
class Route:
    """One URL pattern, flattened: its full route string and its view."""

    route: str
    callback: Callable[..., HttpResponse]

    @property
    def params(self) -> list[str]:
        """Path parameter names, in order."""
        return _PARAM.findall(self.route)


def _walk(patterns: list, prefix: str = "") -> Iterator[Route]:
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _walk(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield Route(route=prefix + str(p.pattern), callback=p.callback)


ALL_ROUTES = list(_walk(get_resolver().url_patterns))
WALKED_ROUTES = [r for r in ALL_ROUTES if not r.route.startswith(_SKIPPED_PREFIXES)]
PRIVATE_ROUTES = [r for r in WALKED_ROUTES if r.route not in PUBLIC_ROUTES]
RECIPE_ROUTES = [r for r in WALKED_ROUTES if "recipe_id" in r.params]


def _ids(routes: list[Route]) -> list[str]:
    return [r.route or "<root>" for r in routes]


@pytest.fixture
def owner(db) -> User:
    """The user who owns every object in `path_values`."""
    return User.objects.create_user(username="route-owner", password="x")


@pytest.fixture
def path_values(owner) -> dict[str, str]:
    """A real object for every path parameter the URLconf uses."""
    recipe = Recipe.objects.create(recipe_name="Owned", owner=owner, servings=4)
    step = Step.objects.create(recipe=recipe, step_text="Stir", index_in_sequence=0)
    group = IngredientGroup.objects.create(recipe=recipe, group_name="Main", index_in_sequence=0)
    ingredient = Ingredient.objects.create(ingredient_name="route-onion")
    iir = IngredientInRecipe.objects.create(
        ingredient=ingredient, ingredient_group=group, index_in_sequence=0
    )
    cuisine = Cuisine.objects.create(cuisine="route-cuisine")
    return {
        "recipe_id": str(recipe.pk),
        "step_id": str(step.pk),
        "group_id": str(group.pk),
        "iir_id": str(iir.pk),
        "ingredient_id": str(ingredient.pk),
        "cuisine_id": str(cuisine.pk),
        "field_name": "recipe_name",
        "uidb64": "MQ",
        "token": "set-password",
    }


def _url(route: Route, values: dict[str, str]) -> str:
    missing = [p for p in route.params if p not in values]
    assert not missing, f"add a value for {missing} to the path_values fixture"
    return "/" + _PARAM.sub(lambda m: values[m.group(1)], route.route)


def _counts() -> tuple[int, ...]:
    return tuple(
        m.objects.count() for m in (Recipe, Step, IngredientGroup, IngredientInRecipe, Ingredient)
    )


def test_login_required_middleware_is_installed() -> None:
    """Login is enforced site-wide, after the user is attached to the request."""
    middleware = settings.MIDDLEWARE
    assert _MIDDLEWARE in middleware
    auth = "django.contrib.auth.middleware.AuthenticationMiddleware"
    assert middleware.index(_MIDDLEWARE) > middleware.index(auth)
    assert middleware.index(_MIDDLEWARE) > middleware.index("django_htmx.middleware.HtmxMiddleware")


@pytest.mark.django_db
def test_undecorated_view_requires_login() -> None:
    """A view with no decorator at all is still behind the login page."""
    from django.contrib.auth.models import AnonymousUser
    from django_htmx.middleware import HtmxDetails

    from nutrisho.middleware import HtmxLoginRequiredMiddleware

    def view(request: HttpRequest) -> HttpResponse:
        return HttpResponse("secret")

    request = RequestFactory().get("/anything/")
    request.user = AnonymousUser()
    request.htmx = HtmxDetails(request)  # type: ignore[attr-defined]
    middleware = HtmxLoginRequiredMiddleware(get_response=lambda r: HttpResponse())  # noqa: ARG005
    response = middleware.process_view(request, view, (), {})
    assert response is not None
    assert response.status_code == 302
    assert response["Location"] == "/accounts/login/?next=/anything/"


def test_public_routes_are_exactly_the_allowlist() -> None:
    """Only the listed routes opt out of login; a new public route must be listed."""
    public = {r.route for r in ALL_ROUTES if not getattr(r.callback, "login_required", True)}
    assert public == PUBLIC_ROUTES


@pytest.mark.django_db
@pytest.mark.parametrize("route", PRIVATE_ROUTES, ids=_ids(PRIVATE_ROUTES))
@pytest.mark.parametrize("method", ["get", "post"])
def test_anonymous_request_redirects_to_login(route: Route, method: str, path_values) -> None:
    """A plain anonymous request gets a 302 to the login page, whatever the method."""
    response = getattr(Client(), method)(_url(route, path_values))
    assert response.status_code == 302
    assert response["Location"].startswith(settings.LOGIN_URL)


@pytest.mark.django_db
@pytest.mark.parametrize("route", PRIVATE_ROUTES, ids=_ids(PRIVATE_ROUTES))
@pytest.mark.parametrize("method", ["get", "post"])
def test_anonymous_htmx_request_gets_hx_redirect(route: Route, method: str, path_values) -> None:
    """An anonymous htmx request gets an empty 200 with HX-Redirect, never a swapped page."""
    response = getattr(Client(), method)(_url(route, path_values), HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert response["HX-Redirect"].startswith(settings.LOGIN_URL)
    assert response.content == b""


@pytest.mark.django_db
@pytest.mark.parametrize("route", RECIPE_ROUTES, ids=_ids(RECIPE_ROUTES))
def test_other_user_gets_404_on_recipe_route(route: Route, path_values) -> None:
    """Another user, even staff, gets 404 on every method a recipe route accepts.

    A method the route does not accept may answer 405, but at least one must
    reach the ownership check, and nothing may be written.
    """
    other = User.objects.create_user(username="route-other", password="x", is_staff=True)
    client = Client()
    client.force_login(other)
    url = _url(route, path_values)
    before = _counts()
    statuses = {
        method: getattr(client, method)(url, HTTP_HX_REQUEST="true").status_code
        for method in ("get", "post")
    }
    assert set(statuses.values()) <= {404, 405}, statuses
    assert 404 in statuses.values(), statuses
    assert _counts() == before
