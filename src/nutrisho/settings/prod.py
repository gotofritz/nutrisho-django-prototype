"""Production settings."""

from pathlib import Path

import environ

# Load .env if present; in real deployments env vars are set by the platform
environ.Env.read_env(Path(__file__).resolve().parent.parent.parent.parent / ".env")

from nutrisho.settings.base import *  # noqa: E402, F401, F403

DEBUG = False
