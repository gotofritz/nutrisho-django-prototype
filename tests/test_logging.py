"""Tests for production logging (issue #43)."""

import logging
import sys
from unittest.mock import patch

import pytest
from django.conf import settings
from django.test import Client


def _reload_base(monkeypatch: pytest.MonkeyPatch):
    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    import nutrisho.settings.base as base_settings

    return base_settings


def test_logging_sends_records_to_stderr() -> None:
    """The root handler writes to stderr, where journald collects it."""
    console = settings.LOGGING["handlers"]["console"]
    assert console["class"] == "logging.StreamHandler"
    assert console["stream"] == "ext://sys.stderr"
    assert settings.LOGGING["root"]["handlers"] == ["console"]


@pytest.mark.parametrize("name", ["django", "django.security", "recipes", "nutrisho"])
def test_app_and_django_loggers_reach_the_console(name: str) -> None:
    """Each logger is configured and propagates to the root console handler."""
    logger = logging.getLogger(name)
    assert logger.propagate is True
    assert name in settings.LOGGING["loggers"]


def test_log_level_defaults_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without LOG_LEVEL, app and Django loggers log at INFO."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    base_settings = _reload_base(monkeypatch)
    assert base_settings.LOGGING["loggers"]["recipes"]["level"] == "INFO"
    assert base_settings.LOGGING["loggers"]["django"]["level"] == "INFO"


def test_log_level_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """LOG_LEVEL sets the level, case-insensitively."""
    monkeypatch.setenv("LOG_LEVEL", "debug")
    base_settings = _reload_base(monkeypatch)
    assert base_settings.LOGGING["loggers"]["recipes"]["level"] == "DEBUG"
    assert base_settings.LOGGING["loggers"]["django"]["level"] == "DEBUG"


def test_security_events_are_never_filtered_below_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """A quiet LOG_LEVEL must not hide django.security warnings."""
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    base_settings = _reload_base(monkeypatch)
    assert base_settings.LOGGING["loggers"]["django.security"]["level"] == "WARNING"


@pytest.mark.django_db
def test_failed_login_is_logged_without_the_password(
    user, caplog: pytest.LogCaptureFixture
) -> None:
    """A wrong password leaves a warning naming the username, never the password."""
    with caplog.at_level(logging.WARNING, logger="recipes"):
        Client().post("/accounts/login/", {"username": user.username, "password": "wrong-pw"})
    records = [r for r in caplog.records if r.name == "recipes.auth"]
    assert len(records) == 1
    assert records[0].levelname == "WARNING"
    assert user.username in records[0].getMessage()
    assert "wrong-pw" not in records[0].getMessage()


@pytest.mark.django_db
def test_csrf_failure_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """A CSRF rejection reaches the log through django.security."""
    with caplog.at_level(logging.WARNING):
        Client(enforce_csrf_checks=True).post(
            "/accounts/login/", {"username": "x", "password": "y"}
        )
    assert any(r.name == "django.security.csrf" for r in caplog.records)


@pytest.mark.django_db
def test_unhandled_exception_is_logged_with_traceback(caplog: pytest.LogCaptureFixture) -> None:
    """A 500 leaves an ERROR on django.request carrying the exception."""
    with patch("nutrisho.health.connection.cursor", side_effect=RuntimeError("boom")):
        response = Client(raise_request_exception=False).get("/healthz")
    assert response.status_code == 500
    records = [r for r in caplog.records if r.name == "django.request" and r.levelname == "ERROR"]
    assert records
    assert records[0].exc_info is not None
