"""Shared fixtures and mocks for the test suite."""

import pytest


@pytest.fixture
def user(db):
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
