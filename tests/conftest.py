"""Shared fixtures and mocks for the test suite."""

import pytest


@pytest.fixture
def user(db):
    from django.contrib.auth.models import User

    try:
        return User.objects.get(username="gotofritz")
    except User.DoesNotExist:
        return User.objects.create_user(username="gotofritz", password="x")
