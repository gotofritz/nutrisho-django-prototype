"""Tests for root URL view."""

import pytest
from django.test import Client


@pytest.fixture
def auth_client(user) -> Client:
    c = Client()
    c.force_login(user)
    return c


@pytest.mark.django_db
def test_root_returns_200(auth_client: Client) -> None:
    response = auth_client.get("/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_root_links_to_recipes(auth_client: Client) -> None:
    response = auth_client.get("/")
    assert b"./recipes/" in response.content


@pytest.mark.django_db
def test_root_unauthenticated_redirects_to_login() -> None:
    response = Client().get("/")
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]
