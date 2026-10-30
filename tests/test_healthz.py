"""Tests for the unauthenticated health check (issue #43)."""

from unittest.mock import patch

import pytest
from django.conf import settings
from django.db import OperationalError
from django.test import Client, override_settings


@pytest.mark.django_db
def test_healthz_returns_200_without_login() -> None:
    """An anonymous GET answers 200 when the database responds."""
    response = Client().get("/healthz")
    assert response.status_code == 200
    assert response.content == b"ok"


@pytest.mark.django_db
def test_healthz_is_never_cached() -> None:
    """Monitors must see the live state, not a cached 200."""
    response = Client().get("/healthz")
    assert "no-store" in response["Cache-Control"]


@pytest.mark.django_db
def test_healthz_answers_head() -> None:
    """HEAD works too; some uptime monitors only send HEAD."""
    response = Client().head("/healthz")
    assert response.status_code == 200


@pytest.mark.django_db
def test_healthz_rejects_post() -> None:
    """Only safe methods are allowed."""
    response = Client().post("/healthz")
    assert response.status_code == 405


@pytest.mark.django_db
def test_healthz_returns_503_and_logs_when_database_fails(caplog: pytest.LogCaptureFixture) -> None:
    """A failing SELECT 1 answers 503 and leaves an error in the log."""
    with patch(
        "django.db.backends.utils.CursorWrapper.execute",
        side_effect=OperationalError("disk I/O error"),
    ):
        response = Client().get("/healthz")
    assert response.status_code == 503
    assert response.content == b"database unavailable"
    assert any(r.levelname == "ERROR" and r.name.startswith("nutrisho") for r in caplog.records)


@pytest.mark.django_db
def test_healthz_is_exempt_from_login_required_middleware() -> None:
    """With login enforced site-wide, the health check stays public."""
    middleware = [*settings.MIDDLEWARE, "django.contrib.auth.middleware.LoginRequiredMiddleware"]
    with override_settings(MIDDLEWARE=middleware):
        assert Client().get("/healthz").status_code == 200
        assert Client().get("/").status_code == 302
