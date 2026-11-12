"""Fixtures for the browser smoke tests (#63).

These tests drive the app in Chromium through pytest-playwright, against
pytest-django's ``live_server``, so the browser-side behaviour the Django test
client never runs is exercised: ``hx-include``, out-of-band swaps,
``HX-Retarget``, the draft-position and split-offset values ``app.js`` adds to
a request, and the bulk-selection panels.

They are marked ``e2e`` and skipped by the default run; ``make e2e`` runs them.
The page needs the built Tailwind CSS (``make css``) and Chromium
(``uv run playwright install chromium``).
"""

from collections.abc import Iterator

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client
from playwright.sync_api import ConsoleMessage, Error, Page


@pytest.fixture(scope="session", autouse=True)
def _allow_orm_beside_playwright() -> Iterator[None]:
    """Let the ORM run in the thread where Playwright's event loop runs.

    Playwright's sync API keeps an asyncio loop running in this thread for the
    whole session, which makes Django refuse every ORM call here, the test
    database's own flush and teardown included, unless
    ``DJANGO_ALLOW_ASYNC_UNSAFE`` is set. Nothing here is async. Session-scoped,
    so it outlasts the database teardown, and set only once a browser test runs.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
        yield


@pytest.fixture(autouse=True)
def _live_database(transactional_db) -> None:
    """Commit each test's rows, so the live server's thread can read them."""


@pytest.fixture(scope="session")
def base_url(live_server) -> str:
    """Point ``page.goto("/...")`` at the live server."""
    return live_server.url


@pytest.fixture
def page(page: Page) -> Iterator[Page]:
    """The Playwright page, failing the test on a script error or a CSP violation.

    A blocked inline script or style (#62) or an exception in ``app.js`` breaks
    behaviour without failing any request, so the console is the only place
    it shows.
    """
    problems: list[str] = []

    def on_console(message: ConsoleMessage) -> None:
        if message.type == "error" and "Content Security Policy" in message.text:
            problems.append(f"{message.text} ({message.location['url']})")

    def on_page_error(error: Error) -> None:
        problems.append(f"{error.name}: {error.message}")

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    yield page
    assert not problems, problems


@pytest.fixture
def signed_in(page: Page, live_server, user: User) -> Page:
    """The page, with the default user's session cookie already set."""
    client = Client()
    client.force_login(user)
    page.context.add_cookies(
        [
            {
                "name": settings.SESSION_COOKIE_NAME,
                "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
                "url": live_server.url,
            }
        ]
    )
    return page
