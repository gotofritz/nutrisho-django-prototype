"""Test settings — hermetic, no .env loading side-effects."""

import os
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("SECRET_KEY", "test-insecure-key-not-for-production")

from nutrisho.settings.base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# Pin to SQLite regardless of any DATABASE_URL in local .env
DATABASES: dict[str, dict[str, Any]] = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "OPTIONS": SQLITE_OPTIONS,  # noqa: F405
        # File-backed, so tests see SQLite's real file locking under concurrent writes
        "TEST": {"NAME": str(Path(tempfile.gettempdir()) / f"nutrisho-test-{os.getpid()}.sqlite3")},
    }
}

# PBKDF2 makes create_user dominate test runtime; MD5 is fine for throwaway users
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
