"""Development settings."""

import environ

from nutrisho.settings.base import *  # noqa: F401, F403

env = environ.Env()

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
