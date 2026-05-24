#!/usr/bin/env bash
# Mirrors Taskfile qa task — used by pre-commit hook when task is not on PATH.
set -e
uv run python -m ruff check src/
uv run python -m ruff format --check src/
.venv/bin/ty check src
uv run pytest -vv -s --cov=src --cov-report=html:htmlcov --cov-fail-under=40
bash .claude/hooks/test-caveman-patterns.sh
