"""Tests for the root URL, which redirects to the recipe list (#74)."""

import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_root_redirects_to_the_recipe_list(auth_client: Client) -> None:
    """`/` has no page of its own: it sends a signed-in user to the recipe list."""
    response = auth_client.get("/")
    assert response.status_code == 302
    assert response["Location"] == reverse("recipes:home")


@pytest.mark.django_db
def test_root_unauthenticated_redirects_to_login() -> None:
    """Root unauthenticated redirects to login."""
    response = Client().get("/")
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]
