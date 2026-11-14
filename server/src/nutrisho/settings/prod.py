"""Production settings."""

from pathlib import Path

import environ
import sentry_sdk

# Load .env if present; in real deployments env vars are set by the platform
environ.Env.read_env(Path(__file__).resolve().parent.parent.parent.parent / ".env")

from nutrisho.settings.base import *  # noqa: F403

DEBUG = False

# Optional error reporting: on only when SENTRY_DSN is set. The Django and
# logging integrations switch on by themselves, so unhandled exceptions and
# ERROR log records both become Sentry events.
SENTRY_DSN = env("SENTRY_DSN", default="")  # noqa: F405
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, send_default_pii=False)
