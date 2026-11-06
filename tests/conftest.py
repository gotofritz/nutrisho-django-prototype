"""Shared fixtures and mocks for the test suite."""

import pytest


@pytest.fixture
def user(db):
    """User."""
    from django.contrib.auth.models import User

    existing = User.objects.filter(username="gotofritz").first()
    if existing is not None:
        return existing
    return User.objects.create_user(username="gotofritz", password="x")


@pytest.fixture
def auth_client(user):
    """Authenticated test client logged in as the default user."""
    from django.test import Client

    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def app_js() -> str:
    """The app's own JavaScript, which ``base.html`` loads on every page (#62)."""
    from pathlib import Path

    from django.contrib.staticfiles import finders

    path = finders.find("js/app.js")
    assert path is not None, "js/app.js is not on the static path"
    return Path(str(path)).read_text()
