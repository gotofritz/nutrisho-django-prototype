"""Development settings."""

import os
from pathlib import Path

import environ

# Safe default so local dev works without a .env file
os.environ.setdefault("SECRET_KEY", "dev-insecure-key-not-for-production")

# Load .env before base.py reads os.environ; missing file is silently ignored
environ.Env.read_env(Path(__file__).resolve().parent.parent.parent.parent / ".env")

from nutrisho.settings.base import *  # noqa: E402, F401, F403

DEBUG = True

_env = environ.Env(ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]))
ALLOWED_HOSTS = _env("ALLOWED_HOSTS")

INSTALLED_APPS = [*INSTALLED_APPS, "debug_toolbar"]  # noqa: F405

MIDDLEWARE = [
    *MIDDLEWARE,  # noqa: F405
    "debug_toolbar.middleware.DebugToolbarMiddleware",
]

INTERNAL_IPS = ["127.0.0.1"]
