# Developer tasks for the whole repository. Run `make` or `make help` to list them.
#
# One Makefile serves both parts (#145). The server targets keep their plain
# names and run inside server/, so a path in ARGS is relative to server/
# (`make test` also accepts `server/tests/...`). Extension targets will take an
# `ext-` prefix once extension/ holds code.
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
SCHEMA ?= server/docs/schema.sql

# Prefix for every server command: it runs in server/, beside its pyproject.toml.
IN_SERVER := cd server &&
# ARGS for pytest, with a leading `server/` dropped from paths given from the root.
TEST_ARGS = $(patsubst server/%,%,$(ARGS))

.PHONY: help audit backup bootstrap check-migrations coverage coverage-badge dev e2e lint lint-fix manage \
	migrate qa release schema seed test test-cov test-hooks typecheck

help: ## List the available targets
	@echo "Usage: make <target> [VAR=value]"
	@echo
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

audit: ## Check the server's locked Python dependencies for known vulnerabilities
	$(IN_SERVER) uv export --all-groups --no-emit-project --format requirements-txt --quiet \
		| uvx pip-audit --strict --disable-pip --requirement /dev/stdin

backup: ## Write the schema to server/docs/schema.sql and a full SQL dump beside it
	$(IN_SERVER) uv run python manage.py backup_db

bootstrap: migrate ## Apply migrations and create the owner superuser from DJANGO_SUPERUSER_* (prompts if unset)
	$(IN_SERVER) uv run python manage.py bootstrap_owner

# Works on a throwaway SQLite file, never db.sqlite3. The dev settings are pinned
# because the test settings ignore DATABASE_URL. SCHEMA is the file to compare.
check-migrations: ## Fail if a model change lacks a migration or server/docs/schema.sql is stale
	$(IN_SERVER) tmp=$$(mktemp -d); \
	trap 'rm -f "$$tmp"/db.sqlite3* "$$tmp"/schema.sql; rmdir "$$tmp"' EXIT; \
	export DJANGO_SETTINGS_MODULE=nutrisho.settings.dev DATABASE_URL="sqlite:///$$tmp/db.sqlite3"; \
	uv run python manage.py migrate --verbosity 0; \
	uv run python manage.py makemigrations --check --dry-run; \
	uv run python manage.py backup_db --schema-only --schema "$$tmp/schema.sql" > /dev/null; \
	diff -u $(abspath $(SCHEMA)) "$$tmp/schema.sql" \
		|| { echo "$(SCHEMA) is stale: run make schema and commit the result" >&2; exit 1; }

coverage: ## Open the latest coverage report (from make test-cov) in a web browser
	$(IN_SERVER) uv run python -m webbrowser "file://$(CURDIR)/server/htmlcov/index.html"

# CI publishes the JSON to the `badges` branch; the README badge renders it.
coverage-badge: ## Write the last test run's coverage total to server/badge-out/coverage.json (shields.io endpoint)
	$(IN_SERVER) mkdir -p badge-out; \
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
	$(IN_SERVER) uv run python manage.py runserver $(PORT)

# The browser smoke tests (#63), which the default pytest run and `make qa` skip.
# They need Chromium: `uv run playwright install chromium`.
e2e: ## Run the browser smoke tests in Chromium (pass extra pytest args as ARGS="...")
	$(IN_SERVER) DJANGO_SETTINGS_MODULE=nutrisho.settings.test uv run pytest --tb=short -m e2e $(TEST_ARGS)

lint: ## Run ruff (non-mutating)
	$(IN_SERVER) uv run ruff check src/ tests/
	$(IN_SERVER) uv run ruff format --check src/ tests/

lint-fix: ## Fix linting issues
	$(IN_SERVER) uv run ruff check --fix src/ tests/
	$(IN_SERVER) uv run ruff format src/ tests/

manage: ## Run a manage.py command under dev settings (pass the command as ARGS="...")
	$(IN_SERVER) uv run python manage.py $(ARGS)

migrate: ## Apply database migrations
	$(IN_SERVER) uv run python manage.py migrate

# Python only, so it needs no network.
qa: lint typecheck check-migrations test-cov ## Run linting, type checking, migration and schema checks, and tests with coverage

# Releases the server alone, tagged server-v<version> (#145). Run from a clean
# checkout. Leaves you on the new branch (or on a detached origin/main if
# nothing is releasable); push it and open a PR. When the PR merges, the CI
# release job tags the version and publishes the GitHub release.
release: ## Start a server release branch: bump the version and CHANGELOG.md in server/ from the commits since the last tag
	git diff --quiet HEAD || { echo "Commit or stash your changes first" >&2; exit 1; }
	git fetch origin main --tags
	git switch --detach origin/main
	$(IN_SERVER) next=$$(uv run cz bump --get-next --yes); \
	git switch -c chore-release-server-v$$next; \
	uv run cz bump --version-files-only --yes; \
	git add pyproject.toml uv.lock CHANGELOG.md; \
	git commit -m "chore(release): server-v$$next"; \
	echo "Push chore-release-server-v$$next and open a PR; CI tags server-v$$next when it merges."

schema: migrate ## Apply migrations, then regenerate server/docs/schema.sql
	$(IN_SERVER) uv run python manage.py backup_db --schema-only

seed: migrate ## Seed sample recipes for a dev user, 'demo' unless ARGS says otherwise (refused in prod)
	$(IN_SERVER) uv run python manage.py seed_demo $(ARGS)

test: ## Run tests, without coverage (pass a path or other pytest args as ARGS="...")
	$(IN_SERVER) DJANGO_SETTINGS_MODULE=nutrisho.settings.test uv run pytest --tb=short $(TEST_ARGS)

test-cov: ## Run tests with coverage, failing under 95%, and write htmlcov/ (pass extra pytest args as ARGS="...")
	$(IN_SERVER) DJANGO_SETTINGS_MODULE=nutrisho.settings.test uv run pytest --tb=short --cov=src --cov-report=html:htmlcov --cov-fail-under=95 $(TEST_ARGS)

test-hooks: ## Run the regression tests for the opt-in caveman hooks in .claude/hooks (not part of qa)
	bash .claude/hooks/test-caveman-patterns.sh

typecheck: ## Run ty for static type checking
	$(IN_SERVER) uv run ty check src tests
