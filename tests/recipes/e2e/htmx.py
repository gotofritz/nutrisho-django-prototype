"""Waiting on htmx from a browser test."""

from playwright.sync_api import Page, expect


def settled(page: Page) -> None:
    """Wait until htmx has finished every request, swap and settle on the page.

    htmx focuses an `[autofocus]` field in a settle task, 20 ms after the swap,
    but the browser may already have focused it on the next frame. A test that
    sees the field focused and types into another one can lose its text to the
    late refocus, so wait for the settle before typing elsewhere.
    """
    expect(page.locator(".htmx-request, .htmx-swapping, .htmx-settling")).to_have_count(0)
