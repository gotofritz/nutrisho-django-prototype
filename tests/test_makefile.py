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
    "backup",
    "bootstrap",
    "coverage",
    "css",
    "css-watch",
    "dev",
    "help",
    "lint",
    "lint-fix",
    "migrate",
    "node-install",
    "qa",
    "test",
    "test-hooks",
    "typecheck",
)

needs_make = pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")


def run_make(*args: str) -> str:
    """Run make in the project root and return its standard output."""
    # Drop settings inherited from an outer `make qa`, so the test sees only its own args.
    env = {k: v for k, v in os.environ.items() if k not in {"MAKEFLAGS", "MFLAGS", "MAKELEVEL"}}
    result = subprocess.run(
        ["make", "--no-print-directory", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


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
    """`make qa` builds CSS, then lints, type-checks, tests and runs hook tests."""
    output = run_make("--dry-run", "qa")
    steps = ["pnpm run css", "ruff check", "ty check", "pytest", "test-caveman-patterns.sh"]

    positions = [output.index(step) for step in steps]
    assert positions == sorted(positions)


@needs_make
def test_test_target_uses_test_settings_and_passes_args():
    """`make test` runs under the test settings and forwards ARGS to pytest."""
    output = run_make("--dry-run", "test", "ARGS=-k healthz")

    assert "DJANGO_SETTINGS_MODULE=nutrisho.settings.test" in output
    assert "--cov-fail-under=95 -k healthz" in output


@needs_make
def test_dev_port_defaults_to_8987_and_can_be_overridden():
    """`make dev` serves on 8987 unless PORT is given."""
    assert "runserver 8987" in run_make("--dry-run", "dev")
    assert "runserver 9000" in run_make("--dry-run", "dev", "PORT=9000")
