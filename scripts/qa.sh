#!/usr/bin/env bash
# Mirrors Taskfile qa task — used by pre-commit hook when task is not on PATH.
set -e
uv run python -m ruff check src/ tests/
uv run python -m ruff format --check src/ tests/
.venv/bin/ty check src tests
DJANGO_SETTINGS_MODULE=nutrisho.settings.test uv run pytest -vv -s --cov=src --cov-report=html:htmlcov --cov-fail-under=95
bash .claude/hooks/test-caveman-patterns.sh
