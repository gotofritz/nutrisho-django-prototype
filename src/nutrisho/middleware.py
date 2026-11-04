"""Site-wide login enforcement that htmx can follow.

Every view requires a signed-in user unless it is marked `@login_not_required`
(the auth views and `/healthz`). `tests/test_route_access.py` walks the URLconf
to keep it that way.
"""

from urllib.parse import quote, urlparse

from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, resolve_url

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _next_target(request: HttpRequest) -> str:
    """Pick where to send the user after login, or "" when nowhere safe is known.

    Decision tree:
    - Boosted HTMX safe methods (full-page navigation): use current URL — the
      destination is a real page, not a fragment.
    - Boosted HTMX unsafe methods (e.g. boosted POST forms): use Referer —
      the POST URL would 405 on GET after login.
    - Non-boosted HTMX (panel/fragment requests): use Referer — the current
      URL is a partial endpoint that would render as a bare fragment after login.
    - Non-HTMX safe methods: use current URL.
    - Non-HTMX unsafe methods: use Referer (POST-only endpoints return 405 on GET).
    """
    htmx = getattr(request, "htmx", None)
    if request.method in _SAFE_METHODS and (not htmx or htmx.boosted):
        return request.get_full_path()
    return urlparse(request.META.get("HTTP_REFERER", "")).path


class HtmxLoginRequiredMiddleware(LoginRequiredMiddleware):
    """Django's LoginRequiredMiddleware, but htmx requests get HX-Redirect instead of a 302.

    A plain 302 makes htmx fetch the login page and swap its HTML into the
    panel target, corrupting the page. An empty 200 with HX-Redirect tells
    htmx to navigate the whole window to the login page instead.
    """

    def handle_no_permission(self, request: HttpRequest, view_func) -> HttpResponse:
        """Redirect to the login page, keeping a `next` that is safe to GET."""
        redirect_to = resolve_url(self.get_login_url(view_func))
        target = _next_target(request)
        if target:
            redirect_to += f"?{self.get_redirect_field_name(view_func)}={quote(target)}"
        if getattr(request, "htmx", None):
            response = HttpResponse()
            response["HX-Redirect"] = redirect_to
            return response
        return redirect(redirect_to)
