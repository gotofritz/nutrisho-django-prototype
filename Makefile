# Developer tasks. Run `make` or `make help` to list them.
#
# A target shows up in `make help` when its rule line ends in `## description`.
# Variables can be set on the command line, e.g. `make dev PORT=9000` or
# `make test ARGS="tests/test_healthz.py -k healthz"`.

.DEFAULT_GOAL := help
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

export DJANGO_SETTINGS_MODULE ?= nutrisho.settings.dev

PORT ?= 8987
ARGS ?=
SCHEMA ?= docs/schema.sql

.PHONY: help audit backup bootstrap check-migrations coverage coverage-badge dev e2e lint lint-fix manage \
	migrate qa release schema seed test test-cov test-hooks typecheck

help: ## List the available targets
	@echo "Usage: make <target> [VAR=value]"
	@echo
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

audit: ## Check locked Python dependencies for known vulnerabilities
	uv export --all-groups --no-emit-project --format requirements-txt --quiet \
		| uvx pip-audit --strict --disable-pip --requirement /dev/stdin

backup: ## Write the schema to docs/schema.sql and a full SQL dump to docs/dump-<timestamp>.sql
	uv run python manage.py backup_db

bootstrap: migrate ## Apply migrations and create the owner superuser from DJANGO_SUPERUSER_* (prompts if unset)
	uv run python manage.py bootstrap_owner

# Works on a throwaway SQLite file, never db.sqlite3. The dev settings are pinned
# because the test settings ignore DATABASE_URL. SCHEMA is the file to compare.
check-migrations: ## Fail if a model change lacks a migration or docs/schema.sql is stale
	tmp=$$(mktemp -d); \
	trap 'rm -f "$$tmp"/db.sqlite3* "$$tmp"/schema.sql; rmdir "$$tmp"' EXIT; \
	export DJANGO_SETTINGS_MODULE=nutrisho.settings.dev DATABASE_URL="sqlite:///$$tmp/db.sqlite3"; \
	uv run python manage.py migrate --verbosity 0; \
	uv run python manage.py makemigrations --check --dry-run; \
	uv run python manage.py backup_db --schema-only --schema "$$tmp/schema.sql" > /dev/null; \
	diff -u $(SCHEMA) "$$tmp/schema.sql" \
		|| { echo "$(SCHEMA) is stale: run make schema and commit the result" >&2; exit 1; }

coverage: ## Open the latest coverage report (from make test-cov) in a web browser
	uv run python -m webbrowser "file://$(CURDIR)/htmlcov/index.html"

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

dev: ## Run the dev server on PORT (default 8987)
	uv run python manage.py runserver $(PORT)

# The browser smoke tests (#63), which the default pytest run and `make qa` skip.
# They need Chromium: `uv run playwright install chromium`.
e2e: ## Run the browser smoke tests in Chromium (pass extra pytest args as ARGS="...")
	DJANGO_SETTINGS_MODULE=nutrisho.settings.test uv run pytest --tb=short -m e2e $(ARGS)

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

# Python only, so it needs no network.
qa: lint typecheck check-migrations test-cov ## Run linting, type checking, migration and schema checks, and tests with coverage

# Run from a clean checkout. Leaves you on the new branch (or on a detached
# origin/main if nothing is releasable); push it and open a PR. When the PR
# merges, the CI release job tags the version and publishes the GitHub release.
release: ## Start a release branch: bump the version and CHANGELOG.md from the commits since the last tag
	git diff --quiet HEAD || { echo "Commit or stash your changes first" >&2; exit 1; }
	git fetch origin main --tags
	git switch --detach origin/main
	next=$$(uv run cz bump --get-next --yes); \
	git switch -c chore-release-v$$next; \
	uv run cz bump --version-files-only --yes; \
	git add pyproject.toml uv.lock CHANGELOG.md; \
	git commit -m "chore(release): v$$next"; \
	echo "Push chore-release-v$$next and open a PR; CI tags v$$next when it merges."

schema: migrate ## Apply migrations, then regenerate docs/schema.sql
	uv run python manage.py backup_db --schema-only

seed: migrate ## Seed sample recipes for a dev user, 'demo' unless ARGS says otherwise (refused in prod)
	uv run python manage.py seed_demo $(ARGS)

test: ## Run tests, without coverage (pass a path or other pytest args as ARGS="...")
	DJANGO_SETTINGS_MODULE=nutrisho.settings.test uv run pytest --tb=short $(ARGS)

test-cov: ## Run tests with coverage, failing under 95%, and write htmlcov/ (pass extra pytest args as ARGS="...")
	DJANGO_SETTINGS_MODULE=nutrisho.settings.test uv run pytest --tb=short --cov=src --cov-report=html:htmlcov --cov-fail-under=95 $(ARGS)

test-hooks: ## Run the regression tests for the opt-in caveman hooks in .claude/hooks (not part of qa)
	bash .claude/hooks/test-caveman-patterns.sh

typecheck: ## Run ty for static type checking
	uv run ty check src tests
