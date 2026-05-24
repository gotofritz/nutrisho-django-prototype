# Plan 001: Settings Configuration

## Status: Done

## Goal

Remove hardcoded secrets and environment-specific config from source code. Make app deployable to different environments without code changes.

## Tasks

- Add `django-environ` to dependencies
- Move `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, and `DATABASES` to `.env`
- Create `.env.example` with safe placeholder values; add `.env` to `.gitignore`
- Create `src/nutrisho/settings/base.py`, `dev.py`, `prod.py`
- Update `manage.py` and `wsgi.py` to use `DJANGO_SETTINGS_MODULE` env var
- Document setup in README

## TDD cycles

1. Test: missing required env var raises `ImproperlyConfigured`
2. Test: dev settings enable `DEBUG=True`
3. Test: settings load correctly in test environment (existing tests still pass)
