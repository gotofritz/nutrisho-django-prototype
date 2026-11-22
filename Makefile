# Developer tasks for the whole repository. Run `make` or `make help` to list them.
#
# One Makefile serves both parts (#145). The server targets keep their plain
# names and run inside server/, so a path in ARGS is relative to server/
# (`make test` also accepts `server/tests/...`). The extension's targets take an
# `ext-` prefix and run inside extension/, with pnpm; `make qa` never needs Node.
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
BROWSER ?= firefox
SCHEMA ?= server/docs/schema.sql

# Prefix for every server command: it runs in server/, beside its pyproject.toml.
IN_SERVER := cd server &&
# Prefix for every extension command: it runs in extension/, beside its package.json.
IN_EXT := cd extension &&
# ARGS for pytest, with a leading `server/` dropped from paths given from the root.
TEST_ARGS = $(patsubst server/%,%,$(ARGS))

.PHONY: help audit backup bootstrap check-migrations coverage coverage-badge dev e2e ext-build ext-dev \
	ext-install ext-qa ext-release ext-test ext-zip lint lint-fix manage migrate qa release schema seed test test-cov test-hooks \
	typecheck

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

# The extension (#162). Node and pnpm versions are pinned in extension/.nvmrc
# and extension/package.json.
#
# pnpm writes node_modules/.modules.yaml on every install, so it stands for
# "installed": the targets below install first when it is missing (a fresh
# checkout) or older than the lockfile or package.json (a pull that changed
# them). It is touched after, because a no-op install may leave it alone.
EXT_INSTALL := $(IN_EXT) pnpm install --frozen-lockfile && touch node_modules/.modules.yaml
EXT_INSTALLED := extension/node_modules/.modules.yaml

$(EXT_INSTALLED): extension/pnpm-lock.yaml extension/package.json
	$(EXT_INSTALL)

ext-build: $(EXT_INSTALLED) ## Build the extension for Firefox and Chrome into extension/.output/
	$(IN_EXT) pnpm build
	$(IN_EXT) pnpm build:chrome

ext-dev: $(EXT_INSTALLED) ## Run the extension in a fresh browser profile, reloading on change (BROWSER=firefox or chrome)
	$(IN_EXT) pnpm $(if $(filter chrome,$(BROWSER)),dev:chrome,dev)

ext-install: ## Install the extension's dependencies from extension/pnpm-lock.yaml
	$(EXT_INSTALL)

ext-preview: $(EXT_INSTALLED) ## Show each state of the sidebar and settings in a plain page, without a browser extension
	$(IN_EXT) pnpm preview

ext-qa: $(EXT_INSTALLED) ## Run the extension's checks: formatting, lint, types, tests, and a build for each browser
	$(IN_EXT) pnpm format:check
	$(IN_EXT) pnpm lint
	$(IN_EXT) pnpm check
	$(IN_EXT) pnpm test
	$(IN_EXT) pnpm build
	$(IN_EXT) pnpm build:chrome

# Releases the extension alone, tagged ext-v<version> (plan 012, M15), as
# `release` does the server, with the server's commitizen and
# extension/.cz.toml, which counts only commits scoped `ext`. When the PR
# merges, the extension workflow tags the version and publishes the release.
ext-release: ## Start an extension release branch: bump the version and CHANGELOG.md in extension/ from the ext commits since the last ext-v tag
	git diff --quiet HEAD || { echo "Commit or stash your changes first" >&2; exit 1; }
	git fetch origin main --tags
	git switch --detach origin/main
	$(IN_EXT) next=$$(uv run --project ../server --frozen cz bump --get-next --yes); \
	git switch -c chore-release-ext-v$$next; \
	uv run --project ../server --frozen cz bump --version-files-only --yes; \
	git add package.json CHANGELOG.md; \
	git commit -m "chore(release): ext-v$$next"; \
	echo "Push chore-release-ext-v$$next and open a PR; CI tags ext-v$$next when it merges."

ext-zip: $(EXT_INSTALLED) ## Zip the extension for each browser, and its sources for AMO, into extension/.output/
	$(IN_EXT) pnpm zip
	$(IN_EXT) pnpm zip:chrome

ext-test: $(EXT_INSTALLED) ## Run the extension's tests (pass a path or other vitest args as ARGS="...")
	$(IN_EXT) pnpm test $(ARGS)

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

test-hooks: ## Run the regression tests for the Claude Code hooks in .claude/hooks (not part of qa)
	bash .claude/hooks/test-caveman-patterns.sh
	bash .claude/hooks/test-check-tdd.sh

typecheck: ## Run ty for static type checking
	$(IN_SERVER) uv run ty check src tests
