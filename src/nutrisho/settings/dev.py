"""Development settings."""

import os
from pathlib import Path

import environ

# Load .env first so it can set SECRET_KEY; fall back only if still unset after
environ.Env.read_env(Path(__file__).resolve().parent.parent.parent.parent / ".env")
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
