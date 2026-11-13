"""Tests for the Makefile that holds the developer tasks."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"
TASKS = (
    "audit",
    "backup",
    "bootstrap",
    "check-migrations",
    "coverage",
    "coverage-badge",
    "dev",
    "e2e",
    "help",
    "lint",
    "lint-fix",
    "manage",
    "migrate",
    "qa",
    "release",
    "schema",
    "seed",
    "test",
    "test-cov",
    "test-hooks",
    "typecheck",
)

needs_make = pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")


def make(
    *args: str, drop_env: frozenset[str] = frozenset(), check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run make in the project root and return the finished process."""
    # Drop settings inherited from an outer `make qa`, so the test sees only its own args.
    dropped = {"MAKEFLAGS", "MFLAGS", "MAKELEVEL"} | drop_env
    env = {k: v for k, v in os.environ.items() if k not in dropped}
    return subprocess.run(
        ["make", "--no-print-directory", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=check,
    )


def run_make(*args: str, drop_env: frozenset[str] = frozenset()) -> str:
    """Run make in the project root and return its standard output."""
    return make(*args, drop_env=drop_env).stdout


def documented_targets() -> dict[str, str]:
    """Map each target that carries a `## description` comment to that description."""
    pattern = re.compile(r"^([a-zA-Z0-9_-]+):.*?## (.+)$", re.MULTILINE)
    return dict(pattern.findall(MAKEFILE.read_text()))


def test_every_task_is_documented():
    """Each developer task is a target with a `##` description, so `help` lists it."""
    assert set(documented_targets()) == set(TASKS)


def test_poe_config_is_gone():
    """The Makefile replaces poethepoet: no `.poe.toml` is left behind."""
    assert not (ROOT / ".poe.toml").exists()
    assert "[tool.poe]" not in (ROOT / "pyproject.toml").read_text()


@needs_make
def test_help_lists_every_target_with_its_description():
    """`make help` prints one line per target, with the description beside it."""
    output = run_make("help")

    for target, description in documented_targets().items():
        assert re.search(
            rf"^\s*{re.escape(target)}\s+{re.escape(description)}$", output, re.MULTILINE
        )


@needs_make
def test_help_is_the_default_goal():
    """A bare `make` prints the same list as `make help`."""
    assert run_make() == run_make("help")


@needs_make
def test_qa_runs_every_check_in_order():
    """`make qa` lints, type-checks, checks migrations and runs the coverage-gated tests."""
    output = run_make("--dry-run", "qa")
    steps = [
        "ruff check",
        "ty check",
        "makemigrations --check --dry-run",
        "--cov-fail-under=95",
    ]

    positions = [output.index(step) for step in steps]
    assert positions == sorted(positions)


@needs_make
def test_qa_needs_no_node():
    """`make qa` is a Python-only gate: no pnpm install or Tailwind build (#68)."""
    output = run_make("--dry-run", "qa")

    assert "pnpm" not in output
    assert "tailwind" not in output


@needs_make
def test_test_target_is_plain_pytest_and_passes_args():
    """`make test` runs pytest quietly under the test settings, with no coverage gate (#68)."""
    output = run_make("--dry-run", "test", "ARGS=tests/test_healthz.py -k healthz")

    assert "DJANGO_SETTINGS_MODULE=nutrisho.settings.test" in output
    assert "pytest --tb=short tests/test_healthz.py -k healthz" in output
    assert "--cov" not in output
    for noisy in (" -vv", " -s "):
        assert noisy not in output


@needs_make
def test_test_cov_target_gates_coverage_and_passes_args():
    """`make test-cov` runs the suite under the test settings with the 95% gate."""
    output = run_make("--dry-run", "test-cov", "ARGS=-k healthz")

    assert "DJANGO_SETTINGS_MODULE=nutrisho.settings.test" in output
    assert "--cov=src" in output
    assert "--cov-fail-under=95 -k healthz" in output
    for noisy in (" -vv", " -s "):
        assert noisy not in output


@needs_make
@pytest.mark.parametrize("target", ["dev", "e2e", "audit"])
def test_no_target_needs_node(target: str):
    """The CSS is hand-written and served as is, so nothing installs Node or builds CSS."""
    output = run_make("--dry-run", target)

    assert "pnpm" not in output
    assert "tailwind" not in output


def test_makefile_has_no_css_build_targets():
    """There is no stylesheet to build, so the Tailwind and Node targets are gone."""
    targets = set(re.findall(r"(?m)^([a-zA-Z0-9_-]+):", MAKEFILE.read_text()))

    assert not targets & {"css", "css-watch", "node-install"}


@needs_make
def test_dev_runs_the_server():
    """`make dev` starts the dev server on PORT."""
    assert "runserver 8987" in run_make("--dry-run", "dev")


@needs_make
def test_e2e_runs_only_the_browser_tests_and_passes_args():
    """`make e2e` runs the `e2e`-marked tests under the test settings (#63)."""
    output = run_make("--dry-run", "e2e", "ARGS=-k login")

    assert "DJANGO_SETTINGS_MODULE=nutrisho.settings.test" in output
    assert "pytest --tb=short -m e2e -k login" in output
    assert "--cov" not in output


@needs_make
def test_qa_leaves_the_browser_tests_out():
    """`make qa` stays Python-only: it never selects the browser tests (#63)."""
    assert "e2e" not in run_make("--dry-run", "qa")


@needs_make
def test_coverage_opens_the_report_on_any_platform():
    """`make coverage` uses Python's webbrowser, not the macOS-only `open` (#68)."""
    output = run_make("--dry-run", "coverage")

    assert "uv run python -m webbrowser" in output
    assert "htmlcov/index.html" in output
    assert not output.startswith("open ")


@needs_make
def test_dev_port_defaults_to_8987_and_can_be_overridden():
    """`make dev` serves on 8987 unless PORT is given."""
    assert "runserver 8987" in run_make("--dry-run", "dev")
    assert "runserver 9000" in run_make("--dry-run", "dev", "PORT=9000")


@needs_make
def test_manage_passes_args_to_manage_py():
    """`make manage` forwards ARGS to manage.py."""
    output = run_make("--dry-run", "manage", "ARGS=delete_recipe --id 42")

    assert "uv run python manage.py delete_recipe --id 42" in output


@needs_make
def test_manage_uses_dev_settings_on_a_fresh_checkout():
    """With no settings module or SECRET_KEY in the environment, `make manage` uses dev."""
    output = run_make(
        "manage",
        "ARGS=shell -c 'from django.conf import settings; print(settings.SETTINGS_MODULE)'",
        drop_env=frozenset({"DJANGO_SETTINGS_MODULE", "SECRET_KEY"}),
    )

    assert output.strip().splitlines()[-1] == "nutrisho.settings.dev"


@needs_make
def test_schema_migrates_then_writes_the_schema_only():
    """`make schema` applies migrations, then regenerates docs/schema.sql alone."""
    output = run_make("--dry-run", "schema")

    migrate = output.index("manage.py migrate")
    backup = output.index("manage.py backup_db --schema-only")
    assert migrate < backup


@needs_make
def test_seed_migrates_then_runs_seed_demo_and_passes_args():
    """`make seed` applies migrations, then runs seed_demo with ARGS (#71)."""
    output = run_make("--dry-run", "seed", "ARGS=--reset")

    migrate = output.index("manage.py migrate")
    seed = output.index("manage.py seed_demo --reset")
    assert migrate < seed


@needs_make
def test_check_migrations_rebuilds_the_schema_in_a_scratch_database():
    """`make check-migrations` migrates a temp DB, writes its schema there, and diffs it."""
    output = run_make("--dry-run", "check-migrations")

    assert "mktemp -d" in output
    assert "DATABASE_URL=" in output
    migrate = output.index("manage.py migrate")
    check = output.index("manage.py makemigrations --check --dry-run")
    backup = output.index("manage.py backup_db --schema-only --schema")
    diff = output.index("diff -u docs/schema.sql")
    assert migrate < check < backup < diff


@needs_make
def test_check_migrations_passes_on_this_checkout():
    """The committed migrations and docs/schema.sql agree with the models."""
    result = make("check-migrations", check=False)

    assert result.returncode == 0, result.stdout + result.stderr


@needs_make
def test_check_migrations_fails_on_a_stale_schema(tmp_path: Path):
    """A schema file that does not match the migrations fails the check."""
    stale = tmp_path / "schema.sql"
    stale.write_text("CREATE TABLE stale (id integer);\n")

    result = make("check-migrations", f"SCHEMA={stale}", check=False)

    assert result.returncode != 0
    assert "make schema" in result.stderr


@needs_make
def test_audit_checks_the_lockfile():
    """`make audit` runs pip-audit over every uv dependency group."""
    output = run_make("--dry-run", "audit")

    assert "uv export --all-groups" in output
    assert "pip-audit --strict" in output


@needs_make
def test_coverage_badge_writes_a_shields_endpoint_from_the_coverage_total():
    """`make coverage-badge` turns the coverage total into a shields.io endpoint JSON."""
    output = run_make("--dry-run", "coverage-badge")

    assert "coverage report --format=total" in output
    assert "badge-out/coverage.json" in output


@needs_make
def test_release_bumps_on_a_fresh_branch_from_main_and_commits():
    """`make release` branches off origin/main, runs `cz bump` on the files only, and commits (#72)."""
    output = run_make("--dry-run", "release")

    fetch = output.index("git fetch origin main --tags")
    branch = output.index("git switch -c chore-release-v")
    bump = output.index("cz bump --version-files-only --yes")
    commit = output.index('git commit -m "chore(release): v')
    assert fetch < branch < bump < commit
    assert "git push" not in output
    assert "git tag" not in output


@needs_make
def test_qa_leaves_the_assistant_hooks_out():
    """The opt-in caveman hooks are not part of the product, so `make qa` skips their tests (#70)."""
    assert "caveman" not in run_make("--dry-run", "qa")


@needs_make
def test_test_hooks_runs_the_caveman_pattern_tests():
    """`make test-hooks` still runs the hook regressions on demand."""
    assert "test-caveman-patterns.sh" in run_make("--dry-run", "test-hooks")


@needs_make
def test_qa_does_not_audit():
    """`make qa` stays offline-friendly: the network-bound audit is a separate target."""
    assert "audit" not in run_make("--dry-run", "qa")


DOCS = (ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "docs" / "developer-guide.md")


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: path.name)
def test_docs_never_call_a_bare_python(doc: Path):
    """Documented commands go through `uv run` or make, never a bare `python`."""
    bare = re.compile(r"(?<!uv run )(?<![\w./-])python3? ")

    assert not bare.findall(doc.read_text())


def test_agents_md_regenerates_the_schema_with_make():
    """AGENTS.md points at `make schema`, which works on a fresh checkout."""
    assert "make schema" in (ROOT / "AGENTS.md").read_text()
