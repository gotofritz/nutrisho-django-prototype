"""Authentication helpers for HTMX-aware login enforcement."""

from functools import wraps
from urllib.parse import quote, urlparse

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseForbidden

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _next_param(request) -> str:
    """Build a safe `next=` query string fragment.

    Decision tree:
    - Boosted HTMX safe methods (full-page navigation): use current URL — the
      destination is a real page, not a fragment.
    - Boosted HTMX unsafe methods (e.g. boosted POST forms): use Referer —
      the POST URL would 405 on GET after login.
    - Non-boosted HTMX (panel/fragment requests): use Referer — the current
      URL is a partial endpoint that would render as a bare fragment after login.
    - Non-HTMX safe methods: use current URL.
    - Non-HTMX unsafe methods: use Referer (POST-only endpoints return 405 on GET).
    Returns an empty string when no safe destination is known.
    """
    htmx = getattr(request, "htmx", None)
    if htmx:
        if htmx.boosted and request.method in _SAFE_METHODS:
            return f"?next={quote(request.get_full_path())}"
        referer = request.META.get("HTTP_REFERER", "")
        if referer:
            path = urlparse(referer).path
            if path:
                return f"?next={quote(path)}"
        return ""
    if request.method in _SAFE_METHODS:
        return f"?next={quote(request.get_full_path())}"
    referer = request.META.get("HTTP_REFERER", "")
    if referer:
        path = urlparse(referer).path
        if path:
            return f"?next={quote(path)}"
    return ""


def htmx_login_required(view_func):
    """Like login_required, but HTMX requests get HX-Redirect instead of a 302.

    A plain 302 from login_required causes the browser to fetch the login page
    and HTMX swaps its HTML into the panel target, corrupting the page.
    Returning HX-Redirect with status 200 tells HTMX to navigate the top-level
    window to the login page instead.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_authenticated:  # type: ignore[union-attr]
            return view_func(request, *args, **kwargs)
        login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
        redirect_to = f"{login_url}{_next_param(request)}"
        if getattr(request, "htmx", None):
            response = HttpResponse()
            response["HX-Redirect"] = redirect_to
            return response
        from django.shortcuts import redirect

        return redirect(redirect_to)

    return _wrapped


_STAFF_ONLY = "Only staff can use the ingredient clean-up tool."


def htmx_staff_required(view_func):
    """Like htmx_login_required, then 403 for a signed-in user who is not staff.

    Anonymous users still go to the login page. An htmx request gets a short
    plain-text 403: the htmx config never swaps a 403, so a full page would only
    be wasted bytes, and the global banner reports the failure. A full-page
    request raises PermissionDenied so Django renders `403.html`.
    """

    @wraps(view_func)
    def _staff_only(request, *args, **kwargs):
        if request.user.is_staff:  # type: ignore[union-attr]
            return view_func(request, *args, **kwargs)
        if getattr(request, "htmx", None):
            return HttpResponseForbidden(_STAFF_ONLY, content_type="text/plain")
        raise PermissionDenied(_STAFF_ONLY)

    return htmx_login_required(_staff_only)
