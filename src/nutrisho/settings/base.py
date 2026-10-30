"""Base settings shared across all environments."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)

# Raises ImproperlyConfigured if SECRET_KEY missing
SECRET_KEY = env("SECRET_KEY")

DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "recipes.apps.RecipesConfig",
    "django_htmx",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "nutrisho.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "nutrisho.wsgi.application"

DATABASES = {
    "default": env.db(default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

# Django's SQLite defaults (rollback journal, DEFERRED transactions) make
# overlapping write requests fail with "database is locked" instead of queueing:
# IMMEDIATE takes the write lock up front, so writers wait out the timeout, and
# WAL lets readers carry on while one writes (issue #38). Options in
# DATABASE_URL win.
SQLITE_OPTIONS = {
    "transaction_mode": "IMMEDIATE",
    "timeout": 20,
    "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
}
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    DATABASES["default"]["OPTIONS"] = {**SQLITE_OPTIONS, **DATABASES["default"].get("OPTIONS", {})}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
INTERNAL_IPS = ["127.0.0.1"]

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/recipes/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# Everything goes to stderr, where journald (or the dev console) collects it.
# Without this, DEBUG=False drops 500s, CSRF failures and django.security
# events on the floor (issue #43). django.security never goes below WARNING,
# so a quiet LOG_LEVEL cannot hide it.
LOG_LEVEL = env.str("LOG_LEVEL", default="INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "plain",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": [], "level": LOG_LEVEL},
        "django.security": {"handlers": [], "level": "WARNING"},
        "recipes": {"handlers": [], "level": LOG_LEVEL},
        "nutrisho": {"handlers": [], "level": LOG_LEVEL},
    },
}
