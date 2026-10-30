"""Test settings — hermetic, no .env loading side-effects."""

import os

os.environ.setdefault("SECRET_KEY", "test-insecure-key-not-for-production")

from nutrisho.settings.base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# Pin to in-memory SQLite regardless of any DATABASE_URL in local .env
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# PBKDF2 makes create_user dominate test runtime; MD5 is fine for throwaway users
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
