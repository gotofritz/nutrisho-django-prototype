"""Tests for root URL view."""

import pytest
from django.test import Client


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.mark.django_db
def test_root_returns_200(client: Client) -> None:
    response = client.get("/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_root_links_to_recipes(client: Client) -> None:
    response = client.get("/")
    assert b"./recipes/" in response.content
