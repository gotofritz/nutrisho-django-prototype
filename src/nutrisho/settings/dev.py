"""Development settings."""

import os

import environ

# Safe default so local dev works without a .env file
os.environ.setdefault("SECRET_KEY", "dev-insecure-key-not-for-production")

from nutrisho.settings.base import *  # noqa: F401, F403

DEBUG = True

_env = environ.Env(ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]))
ALLOWED_HOSTS = _env("ALLOWED_HOSTS")

INSTALLED_APPS = [*INSTALLED_APPS, "debug_toolbar"]  # noqa: F405

MIDDLEWARE = [
    *MIDDLEWARE,  # noqa: F405
    "debug_toolbar.middleware.DebugToolbarMiddleware",
]

INTERNAL_IPS = ["127.0.0.1"]
