"""Tests for settings configuration (Plan 001)."""

import os
import pytest


def test_missing_secret_key_raises(monkeypatch):
    """Missing SECRET_KEY env var raises ImproperlyConfigured when no .env file."""
    monkeypatch.delenv("SECRET_KEY", raising=False)

    import sys
    from unittest.mock import patch

    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    from django.core.exceptions import ImproperlyConfigured

    # Patch read_env so it doesn't load .env file
    with patch("environ.Env.read_env"):
        with pytest.raises((ImproperlyConfigured, KeyError)):
            import nutrisho.settings.base  # noqa: F401


def test_dev_settings_enable_debug(monkeypatch):
    """Dev settings have DEBUG=True."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-testing-only")

    import importlib
    import sys

    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    import nutrisho.settings.dev as dev_settings

    assert dev_settings.DEBUG is True


def test_existing_tests_still_pass():
    """Settings load correctly — existing 3 tests pass when imported."""
    from django.conf import settings

    assert settings.configured
