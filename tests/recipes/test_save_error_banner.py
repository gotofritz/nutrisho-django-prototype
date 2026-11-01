"""Tests for the global HTMX save-error banner (#37).

The listener itself runs in the browser; these tests pin the markup and the
wiring in ``base.html`` so every page that extends it carries both.
"""

import re

import pytest


@pytest.fixture
def home_html(auth_client) -> str:
    """Rendered recipe list, which extends ``base.html``."""
    response = auth_client.get("/recipes/")
    assert response.status_code == 200
    return response.content.decode()


def _banner(html: str) -> str:
    match = re.search(r'<div[^>]*id="save-error".*?</div>', html, flags=re.DOTALL)
    assert match, "save-error banner missing from base.html"
    return match.group(0)


@pytest.mark.django_db
def test_banner_is_rendered_hidden(home_html):
    """The banner is on every page but hidden until a request fails."""
    opening_tag = re.search(r'<div[^>]*id="save-error"[^>]*>', home_html)
    assert opening_tag
    assert " hidden" in opening_tag.group(0)


@pytest.mark.django_db
def test_banner_is_announced_to_screen_readers(home_html):
    """The banner is a live alert so assistive tech reads it when shown."""
    assert 'role="alert"' in _banner(home_html)


@pytest.mark.django_db
def test_banner_has_message_and_dismiss_button(home_html):
    """The banner carries a message slot and a dismiss button."""
    banner = _banner(home_html)
    assert 'id="save-error-message"' in banner
    assert 'id="save-error-dismiss"' in banner


@pytest.mark.django_db
def test_banner_is_rendered_once_in_body(home_html):
    """There is exactly one banner, inside <body>."""
    assert home_html.count('id="save-error"') == 1
    assert 'id="save-error"' in home_html.split("<body", 1)[1]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "event_name",
    ["htmx:responseError", "htmx:sendError", "htmx:timeout"],
)
def test_listener_handles_every_failure_event(home_html, event_name):
    """One global listener covers server errors, dropped connections and timeouts."""
    assert f"'{event_name}'" in home_html


@pytest.mark.django_db
def test_listener_messages(home_html):
    """The messages say the change was not saved, with a reload hint on 403."""
    assert "Your change was not saved." in home_html
    assert "Reload the page and try again." in home_html
    assert "Check your connection and try again." in home_html


@pytest.mark.django_db
def test_error_responses_are_not_swapped(home_html):
    """Non-2xx/422 responses are not swapped, so the open edit form keeps its text."""
    config = re.search(r'name="htmx-config" content=\'([^\']*)\'', home_html)
    assert config
    assert '{"code":".*","swap":false,"error":true}' in config.group(1)
