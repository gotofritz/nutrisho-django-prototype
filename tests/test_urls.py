"""Tests for the project URLconf."""

import importlib
from collections.abc import Iterator
from types import ModuleType

import pytest
from django.test import override_settings
from django.urls import clear_url_caches

import nutrisho.urls


@pytest.fixture
def reload_urls() -> Iterator[ModuleType]:
    """Yield nutrisho.urls for reloading under overridden settings; restore after."""
    yield nutrisho.urls
    importlib.reload(nutrisho.urls)
    clear_url_caches()


def _has_debug_route(urls: ModuleType) -> bool:
    return any(str(p.pattern) == "__debug__/" for p in urls.urlpatterns)


def test_debug_route_absent_when_toolbar_not_installed(reload_urls: ModuleType) -> None:
    """DEBUG alone does not mount the toolbar; it needs the installed app."""
    with override_settings(DEBUG=True):
        importlib.reload(reload_urls)
    assert not _has_debug_route(reload_urls)


def test_debug_route_present_when_toolbar_installed(reload_urls: ModuleType) -> None:
    """The toolbar route is mounted whenever debug_toolbar is an installed app."""
    from django.conf import settings

    with override_settings(INSTALLED_APPS=[*settings.INSTALLED_APPS, "debug_toolbar"]):
        importlib.reload(reload_urls)
    assert _has_debug_route(reload_urls)
