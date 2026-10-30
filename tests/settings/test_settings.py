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

    with patch("environ.Env.read_env"), pytest.raises((ImproperlyConfigured, KeyError)):
        import nutrisho.settings.prod  # noqa: F401


def test_dev_settings_enable_debug():
    """Dev settings have DEBUG=True and provide a safe SECRET_KEY default."""
    import sys

    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    import nutrisho.settings.dev as dev_settings

    assert dev_settings.DEBUG is True
    assert dev_settings.SECRET_KEY


def test_dev_settings_no_debug_toolbar_in_prod():
    """debug_toolbar not in prod INSTALLED_APPS."""
    import os
    import sys

    os.environ.setdefault("SECRET_KEY", "test-secret")

    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    import nutrisho.settings.prod as prod_settings

    assert "debug_toolbar" not in prod_settings.INSTALLED_APPS


def test_test_settings_use_in_memory_db():
    """Test settings pin DATABASE to :memory: so local .env DATABASE_URL is ignored."""
    import sys

    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    import nutrisho.settings.test as test_settings

    assert test_settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
    assert test_settings.DATABASES["default"]["NAME"] == ":memory:"


def test_test_settings_use_fast_password_hasher():
    """Test settings use MD5 so create_user doesn't pay for PBKDF2 in every test."""
    import sys

    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    import nutrisho.settings.test as test_settings

    assert test_settings.PASSWORD_HASHERS == ["django.contrib.auth.hashers.MD5PasswordHasher"]


def test_dev_allowed_hosts_reads_env(monkeypatch):
    """Dev ALLOWED_HOSTS reads from env, not hardcoded."""
    import sys

    monkeypatch.setenv("ALLOWED_HOSTS", "myhost.example.com,staging.example.com")
    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    import nutrisho.settings.dev as dev_settings

    assert "myhost.example.com" in dev_settings.ALLOWED_HOSTS


def test_bare_settings_package_raises(monkeypatch):
    """DJANGO_SETTINGS_MODULE=nutrisho.settings raises ImproperlyConfigured."""
    import sys

    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "nutrisho.settings")
    for mod in list(sys.modules.keys()):
        if mod == "nutrisho.settings":
            del sys.modules[mod]

    from django.core.exceptions import ImproperlyConfigured

    with pytest.raises(ImproperlyConfigured, match=r"nutrisho\.settings is not a valid"):
        import nutrisho.settings  # noqa: F401


def test_existing_tests_still_pass():
    """Settings load correctly in test environment."""
    from django.conf import settings

    assert settings.configured


SQLITE_OPTIONS = {
    "transaction_mode": "IMMEDIATE",
    "timeout": 20,
    "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
}


def test_sqlite_database_is_configured_for_concurrent_writes(monkeypatch):
    """A SQLite DATABASE_URL gets WAL, IMMEDIATE transactions and a 20 s busy timeout."""
    import sys

    monkeypatch.setenv("DATABASE_URL", "sqlite:////var/lib/nutrisho/db.sqlite3")
    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    import nutrisho.settings.base as base_settings

    assert base_settings.DATABASES["default"]["OPTIONS"] == SQLITE_OPTIONS


def test_sqlite_options_in_database_url_win(monkeypatch):
    """Options given in DATABASE_URL override the SQLite defaults."""
    import sys

    monkeypatch.setenv("DATABASE_URL", "sqlite:////var/lib/nutrisho/db.sqlite3?timeout=5")
    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    import nutrisho.settings.base as base_settings

    assert base_settings.DATABASES["default"]["OPTIONS"] == {**SQLITE_OPTIONS, "timeout": 5}


def test_non_sqlite_database_gets_no_sqlite_options(monkeypatch):
    """SQLite pragmas and transaction modes are not applied to other engines."""
    import sys

    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@localhost/nutrisho")
    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    import nutrisho.settings.base as base_settings

    assert "transaction_mode" not in base_settings.DATABASES["default"].get("OPTIONS", {})


def test_test_settings_use_the_same_sqlite_options():
    """Tests run with the shipped SQLite options, on a file so locking is real."""
    import sys

    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    import nutrisho.settings.test as test_settings

    assert test_settings.DATABASES["default"]["OPTIONS"] == SQLITE_OPTIONS
    assert test_settings.DATABASES["default"]["TEST"]["NAME"].endswith(".sqlite3")


def _reload_prod(monkeypatch):
    import sys

    monkeypatch.setenv("SECRET_KEY", "test-secret")
    for mod in list(sys.modules.keys()):
        if "nutrisho.settings" in mod:
            del sys.modules[mod]

    import nutrisho.settings.prod as prod_settings

    return prod_settings


def test_prod_initialises_sentry_when_dsn_set(monkeypatch):
    """SENTRY_DSN turns on Sentry, without sending personal data."""
    from unittest.mock import patch

    monkeypatch.setenv("SENTRY_DSN", "https://key@o0.ingest.sentry.io/0")
    with patch("environ.Env.read_env"), patch("sentry_sdk.init") as init:
        _reload_prod(monkeypatch)

    init.assert_called_once()
    assert init.call_args.kwargs["dsn"] == "https://key@o0.ingest.sentry.io/0"
    assert init.call_args.kwargs["send_default_pii"] is False


def test_prod_skips_sentry_without_dsn(monkeypatch):
    """No SENTRY_DSN, no Sentry."""
    from unittest.mock import patch

    monkeypatch.delenv("SENTRY_DSN", raising=False)
    with patch("environ.Env.read_env"), patch("sentry_sdk.init") as init:
        _reload_prod(monkeypatch)

    init.assert_not_called()
