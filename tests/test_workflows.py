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
def test_only_the_badge_and_release_jobs_can_write(path: Path):
    """A job widens the token only to publish the coverage badge or a release."""
    for name, job in load(path)["jobs"].items():
        if "permissions" in job:
            assert name in {"badge", "release"}
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


def release_workflow() -> dict[str, Any]:
    """`ci.yml` cut down to its release job, for the step helpers above."""
    return {"jobs": {"release": load(ROOT / ".github/workflows/ci.yml")["jobs"]["release"]}}


def test_release_job_runs_only_after_qa_passes_on_main():
    """A version is released only from a green push to main (#72)."""
    release = release_workflow()["jobs"]["release"]

    assert release["needs"] == "qa"
    assert "needs.qa.result == 'success'" in release["if"]
    assert "github.event_name == 'push'" in release["if"]
    assert "github.ref == 'refs/heads/main'" in release["if"]


def test_release_job_runs_no_project_code():
    """The write-scoped release job checks out without saved credentials and runs only gh."""
    workflow = release_workflow()
    (checkout,) = steps_using(workflow, "actions/checkout")
    scripts = run_lines(workflow)

    assert checkout["with"]["persist-credentials"] is False
    assert len(steps(workflow)) == 2
    for command in ("uv ", "make ", "pnpm ", "python"):
        assert command not in scripts


def test_release_job_publishes_the_changelog_section_for_a_new_tag():
    """The release job tags `v<version>` once and uses its CHANGELOG.md section as notes."""
    scripts = run_lines(release_workflow())

    assert 'tag="v$version"' in scripts
    assert 'gh release view "$tag"' in scripts
    assert "CHANGELOG.md" in scripts
    assert 'gh release create "$tag"' in scripts
    assert '--target "$GITHUB_SHA"' in scripts


def qa_job_steps() -> list[dict[str, Any]]:
    """The steps of the CI `qa` job, in order."""
    return load(ROOT / ".github/workflows/ci.yml")["jobs"]["qa"]["steps"]


def test_ci_builds_the_css_that_qa_skips():
    """`make qa` is Python-only, so CI builds the Tailwind CSS itself, before QA (#68)."""
    runs = [step.get("run", "") for step in qa_job_steps()]

    assert runs.index("make css") < runs.index("make qa")


PR_TITLE = ROOT / ".github/workflows/pr-title.yml"


def test_pr_titles_are_linted_when_opened_or_edited():
    """The PR title becomes the squash-merge subject, so CI checks it on every change (#68)."""
    triggers = yaml.safe_load(PR_TITLE.read_text())[True]  # PyYAML reads `on:` as True

    assert set(triggers) == {"pull_request"}
    assert {"opened", "edited", "reopened", "synchronize"} <= set(triggers["pull_request"]["types"])


def test_pr_title_is_checked_with_commitizen_from_the_environment():
    """`cz check` lints the title, passed through `env` so it is never spliced into the script."""
    workflow = load(PR_TITLE)
    (step,) = [step for step in steps(workflow) if "cz check" in step.get("run", "")]

    assert step["env"]["PR_TITLE"] == "${{ github.event.pull_request.title }}"
    assert 'cz check --message "$PR_TITLE"' in step["run"]
    assert "github.event" not in step["run"]
