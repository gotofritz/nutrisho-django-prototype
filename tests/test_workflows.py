"""Tests for the GitHub Actions workflows: token scope, pinning and run limits."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
SHA_PIN = re.compile(r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")
EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+$")

workflow_files = pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)


def load(path: Path) -> dict[str, Any]:
    """Parse a workflow file."""
    return yaml.safe_load(path.read_text())


def steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Every step of every job in a workflow."""
    return [step for job in workflow["jobs"].values() for step in job["steps"]]


def steps_using(workflow: dict[str, Any], action: str) -> list[dict[str, Any]]:
    """The steps that run the given action, e.g. `astral-sh/setup-uv`."""
    return [step for step in steps(workflow) if step.get("uses", "").startswith(f"{action}@")]


def run_lines(workflow: dict[str, Any]) -> str:
    """All `run:` scripts of a workflow, joined."""
    return "\n".join(step.get("run", "") for step in steps(workflow))


def test_there_are_workflows():
    """The parametrised tests below have something to check."""
    assert WORKFLOWS


@workflow_files
def test_token_is_read_only_by_default(path: Path):
    """The workflow-level token can only read contents."""
    assert load(path)["permissions"] == {"contents": "read"}


@workflow_files
def test_only_the_badge_job_can_write(path: Path):
    """A job widens the token only to publish the coverage badge."""
    for name, job in load(path)["jobs"].items():
        if "permissions" in job:
            assert name == "badge"
            assert job["permissions"] == {"contents": "write"}


@workflow_files
def test_actions_are_pinned_to_commit_shas(path: Path):
    """Every action is pinned to a full commit SHA, which a tag move cannot change."""
    for step in steps(load(path)):
        if "uses" in step:
            assert SHA_PIN.match(step["uses"]), step["uses"]


@workflow_files
def test_actions_run_on_their_own_node_version(path: Path):
    """No action needs to be forced onto a newer Node runtime."""
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24" not in path.read_text()


@workflow_files
def test_superseded_runs_are_grouped(path: Path):
    """A newer run on the same ref cancels or queues behind the older one."""
    concurrency = load(path)["concurrency"]

    assert "github.ref" in concurrency["group"]
    assert "cancel-in-progress" in concurrency


@workflow_files
def test_every_job_has_a_timeout(path: Path):
    """A hung job stops long before the six-hour default."""
    for job in load(path)["jobs"].values():
        assert 0 < job["timeout-minutes"] <= 30


@workflow_files
def test_uv_version_is_pinned(path: Path):
    """setup-uv installs one exact uv version, not whatever is latest."""
    for step in steps_using(load(path), "astral-sh/setup-uv"):
        assert EXACT_VERSION.match(step["with"]["version"])


@workflow_files
def test_pnpm_version_comes_from_package_json(path: Path):
    """pnpm/action-setup reads the `packageManager` pin rather than its own version."""
    for step in steps_using(load(path), "pnpm/action-setup"):
        assert "version" not in step.get("with", {})


@workflow_files
def test_nothing_is_installed_outside_the_lockfiles(path: Path):
    """No step installs packages with pip or apt; uv and pnpm use the lockfiles."""
    scripts = run_lines(load(path))

    assert "pip install" not in scripts
    assert "apt-get" not in scripts


def test_package_json_pins_pnpm():
    """`packageManager` names one exact pnpm version for CI, corepack and developers."""
    package = json.loads((ROOT / "package.json").read_text())

    name, _, version = package["packageManager"].partition("@")
    assert name == "pnpm"
    assert EXACT_VERSION.match(version)


def test_ci_installs_python_dependencies_from_the_lockfile():
    """CI fails when uv.lock is out of date instead of re-resolving it."""
    assert "uv sync --locked --all-groups" in run_lines(load(ROOT / ".github/workflows/ci.yml"))


def test_ci_builds_the_badge_with_make():
    """The badge JSON is written by `make coverage-badge` in the QA job."""
    ci = load(ROOT / ".github/workflows/ci.yml")

    assert "make coverage-badge" in run_lines({"jobs": {"qa": ci["jobs"]["qa"]}})


def test_badge_job_runs_no_code_of_its_own():
    """The write-scoped badge job only downloads the badge JSON and publishes it."""
    badge = load(ROOT / ".github/workflows/ci.yml")["jobs"]["badge"]

    assert all("run" not in step for step in badge["steps"])
