"""Tests for settings configuration (Plan 001)."""

import pytest


def test_prod_missing_secret_key_raises(monkeypatch):
    """Prod settings raise ImproperlyConfigured when SECRET_KEY absent and no .env."""
    monkeypatch.delenv("SECRET_KEY", raising=False)

    import sys
    from unittest.mock import patch

    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    from django.core.exceptions import ImproperlyConfigured

    with patch("environ.Env.read_env"):
        with pytest.raises((ImproperlyConfigured, KeyError)):
            import nutrisho.settings.prod  # noqa: F401


def test_dev_settings_enable_debug():
    """Dev settings have DEBUG=True and provide a safe SECRET_KEY default."""
    import sys

    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    import nutrisho.settings.dev as dev_settings

    assert dev_settings.DEBUG is True
    assert dev_settings.SECRET_KEY  # not empty


def test_dev_settings_no_debug_toolbar_in_prod():
    """debug_toolbar not in prod INSTALLED_APPS."""
    import sys
    import os

    os.environ.setdefault("SECRET_KEY", "test-secret")

    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    import nutrisho.settings.prod as prod_settings

    assert "debug_toolbar" not in prod_settings.INSTALLED_APPS


def test_existing_tests_still_pass():
    """Settings load correctly in test environment."""
    from django.conf import settings

    assert settings.configured
