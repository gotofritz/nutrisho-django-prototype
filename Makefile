# Developer tasks. Run `make` or `make help` to list them.
#
# A target shows up in `make help` when its rule line ends in `## description`.
# Variables can be set on the command line, e.g. `make dev PORT=9000` or
# `make test ARGS="-k healthz"`.

.DEFAULT_GOAL := help
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

export DJANGO_SETTINGS_MODULE ?= nutrisho.settings.dev

PORT ?= 8987
ARGS ?=

.PHONY: help backup bootstrap coverage css css-watch dev lint lint-fix migrate \
	node-install qa test test-hooks typecheck

help: ## List the available targets
	@echo "Usage: make <target> [VAR=value]"
	@echo
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

backup: ## Write the schema to docs/schema.sql and a full SQL dump to docs/dump-<timestamp>.sql
	uv run python manage.py backup_db

bootstrap: migrate ## Apply migrations and create the owner superuser from DJANGO_SUPERUSER_* (prompts if unset)
	uv run python manage.py bootstrap_owner

coverage: ## Open the latest coverage report in a web browser
	open htmlcov/index.html

css: node-install ## Build Tailwind CSS (minified)
	pnpm run css

css-watch: node-install ## Watch and rebuild Tailwind CSS on changes
	pnpm run css:watch

dev: css ## Run the dev server on PORT (default 8987); builds CSS first
	uv run python manage.py runserver $(PORT)

lint: ## Run ruff (non-mutating)
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

lint-fix: ## Fix linting issues
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

migrate: ## Apply database migrations
	uv run python manage.py migrate

node-install: ## Install Node dependencies via pnpm
	pnpm install

qa: css lint typecheck test test-hooks ## Run CSS build, linting, type checking, tests, and hook regressions

test: ## Run tests with coverage (pass extra pytest args as ARGS="...")
	DJANGO_SETTINGS_MODULE=nutrisho.settings.test uv run pytest -vv -s --cov=src --cov-report=html:htmlcov --cov-fail-under=95 $(ARGS)

test-hooks: ## Run shell regression tests for .claude/hooks
	bash .claude/hooks/test-caveman-patterns.sh

typecheck: ## Run ty for static type checking
	uv run ty check src tests
