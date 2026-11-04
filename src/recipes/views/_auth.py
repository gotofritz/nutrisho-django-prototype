"""Access helpers for views; login itself is enforced by `HtmxLoginRequiredMiddleware`."""

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404

from recipes.models import Recipe
from recipes.views._types import AuthedRequest


def owned_recipe(request: AuthedRequest, recipe_id: int) -> Recipe:
    """Return the signed-in user's recipe, or 404 when it is missing or someone else's.

    404 rather than 403, so a recipe id never reveals that another user has it.
    """
    return get_object_or_404(Recipe, id=recipe_id, owner=request.user)


_STAFF_ONLY = "Only staff can use the ingredient clean-up tool."


def htmx_staff_required(view_func):
    """403 for a signed-in user who is not staff.

    Anonymous users never get here: the login middleware sends them to the
    login page first. An htmx request gets a short plain-text 403: the htmx
    config never swaps a 403, so a full page would only be wasted bytes, and
    the global banner reports the failure. A full-page request raises
    PermissionDenied so Django renders `403.html`.
    """

    @wraps(view_func)
    def _staff_only(request, *args, **kwargs):
        if request.user.is_staff:  # type: ignore[union-attr]
            return view_func(request, *args, **kwargs)
        if getattr(request, "htmx", None):
            return HttpResponseForbidden(_STAFF_ONLY, content_type="text/plain")
        raise PermissionDenied(_STAFF_ONLY)

    return _staff_only
