"""Shared fixtures and mocks for the test suite."""

import pytest


@pytest.fixture
def user(db):
    from django.contrib.auth.models import User

    user, _ = User.objects.get_or_create(
        username="gotofritz", defaults={"password": "x"}
    )
    return user
