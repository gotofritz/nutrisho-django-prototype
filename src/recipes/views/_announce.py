"""Screen-reader announcements for changes a swap alone does not convey (#61)."""

from django.http import HttpResponse
from django_htmx.http import trigger_client_event


def announce(response: HttpResponse, message: str) -> HttpResponse:
    """Ask the page to read ``message`` out through its polite live region.

    A deleted row just vanishes from the page, so a screen reader hears nothing;
    ``base.html`` listens for the ``announce`` event this sets in ``HX-Trigger``.
    """
    return trigger_client_event(response, "announce", {"message": message})
