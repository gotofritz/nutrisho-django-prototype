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

.PHONY: help audit backup bootstrap coverage coverage-badge css css-watch dev lint lint-fix manage \
	migrate node-install qa schema test test-hooks typecheck

help: ## List the available targets
	@echo "Usage: make <target> [VAR=value]"
	@echo
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

audit: ## Check locked Python and Node dependencies for known vulnerabilities
	uv export --all-groups --no-emit-project --format requirements-txt --quiet \
		| uvx pip-audit --strict --disable-pip --requirement /dev/stdin
	pnpm audit --audit-level=high

backup: ## Write the schema to docs/schema.sql and a full SQL dump to docs/dump-<timestamp>.sql
	uv run python manage.py backup_db

bootstrap: migrate ## Apply migrations and create the owner superuser from DJANGO_SUPERUSER_* (prompts if unset)
	uv run python manage.py bootstrap_owner

coverage: ## Open the latest coverage report in a web browser
	open htmlcov/index.html

# CI publishes the JSON to the `badges` branch; the README badge renders it.
coverage-badge: ## Write the last test run's coverage total to badge-out/coverage.json (shields.io endpoint)
	mkdir -p badge-out
	pct=$$(uv run coverage report --format=total); \
	if [ "$$pct" -ge 90 ]; then color=brightgreen; \
	elif [ "$$pct" -ge 80 ]; then color=green; \
	elif [ "$$pct" -ge 70 ]; then color=yellowgreen; \
	elif [ "$$pct" -ge 60 ]; then color=yellow; \
	elif [ "$$pct" -ge 50 ]; then color=orange; \
	else color=red; fi; \
	printf '{"schemaVersion": 1, "label": "coverage", "message": "%s%%", "color": "%s"}\n' \
		"$$pct" "$$color" > badge-out/coverage.json

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

manage: ## Run a manage.py command under dev settings (pass the command as ARGS="...")
	uv run python manage.py $(ARGS)

migrate: ## Apply database migrations
	uv run python manage.py migrate

node-install: ## Install Node dependencies via pnpm
	pnpm install

qa: css lint typecheck test test-hooks ## Run CSS build, linting, type checking, tests, and hook regressions

schema: migrate ## Apply migrations, then regenerate docs/schema.sql
	uv run python manage.py backup_db --schema-only

test: ## Run tests with coverage (pass extra pytest args as ARGS="...")
	DJANGO_SETTINGS_MODULE=nutrisho.settings.test uv run pytest -vv -s --cov=src --cov-report=html:htmlcov --cov-fail-under=95 $(ARGS)

test-hooks: ## Run shell regression tests for .claude/hooks
	bash .claude/hooks/test-caveman-patterns.sh

typecheck: ## Run ty for static type checking
	uv run ty check src tests
