"""Tests for the GitHub Actions workflows: token scope, pinning and run limits."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]  # the repository; the server is ROOT / "server"
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
def test_no_workflow_sets_up_node(path: Path):
    """The app has no Node toolchain since Tailwind went, so no job installs pnpm."""
    assert not steps_using(load(path), "pnpm/action-setup")
    assert "pnpm" not in run_lines(load(path))


@workflow_files
def test_nothing_is_installed_outside_the_lockfiles(path: Path):
    """No step installs packages with pip or apt; uv uses the lockfile."""
    scripts = run_lines(load(path))

    assert "pip install" not in scripts
    assert "apt-get" not in scripts


def test_there_is_no_node_project_outside_the_extension():
    """No package.json or pnpm lockfile for the server: its stylesheets are plain CSS."""
    for directory in (ROOT, ROOT / "server"):
        for name in ("package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml"):
            assert not (directory / name).exists(), directory / name


def triggers(path: Path) -> dict[str, Any]:
    """The `on:` block of a workflow, which PyYAML reads as the key True."""
    return yaml.safe_load(path.read_text())[True]


SERVER_WORKFLOWS = [
    ROOT / ".github/workflows/server.yml",
    ROOT / ".github/workflows/server-audit.yml",
]


@pytest.mark.parametrize("path", SERVER_WORKFLOWS, ids=lambda path: path.name)
def test_server_workflows_skip_extension_only_changes(path: Path):
    """A change under `extension/` alone never runs the server's checks (#145)."""
    for event in ("push", "pull_request"):
        assert "extension/**" in triggers(path)[event]["paths-ignore"]


def test_the_audit_still_runs_weekly():
    """A new advisory against an unchanged lockfile still turns the audit red."""
    assert triggers(ROOT / ".github/workflows/server-audit.yml")["schedule"]


@pytest.mark.parametrize("job", ["qa", "e2e"])
def test_server_dependencies_are_installed_in_the_server_directory(job: str):
    """`server/` holds its own pyproject.toml and uv.lock, so uv runs there (#145)."""
    workflow = {"jobs": {job: load(ROOT / ".github/workflows/server.yml")["jobs"][job]}}

    for step in steps(workflow):
        if step.get("run", "").startswith("uv "):
            assert step["working-directory"] == "server", step["run"]


def test_ci_installs_python_dependencies_from_the_lockfile():
    """CI fails when uv.lock is out of date instead of re-resolving it."""
    assert "uv sync --locked --all-groups" in run_lines(load(ROOT / ".github/workflows/server.yml"))


def test_ci_builds_the_badge_with_make():
    """The badge JSON is written by `make coverage-badge` in the QA job."""
    ci = load(ROOT / ".github/workflows/server.yml")

    assert "make coverage-badge" in run_lines({"jobs": {"qa": ci["jobs"]["qa"]}})


def test_badge_job_runs_no_code_of_its_own():
    """The write-scoped badge job only downloads the badge JSON and publishes it."""
    badge = load(ROOT / ".github/workflows/server.yml")["jobs"]["badge"]

    assert all("run" not in step for step in badge["steps"])


def release_workflow() -> dict[str, Any]:
    """`server.yml` cut down to its release job, for the step helpers above."""
    return {"jobs": {"release": load(ROOT / ".github/workflows/server.yml")["jobs"]["release"]}}


def test_release_job_runs_only_after_qa_passes_on_main():
    """A version is released only from a green push to main (#72)."""
    release = release_workflow()["jobs"]["release"]

    assert release["needs"] == "qa"
    assert "needs.qa.result == 'success'" in release["if"]
    assert "github.event_name == 'push'" in release["if"]
    assert "github.ref == 'refs/heads/main'" in release["if"]


def test_release_job_treats_the_unprefixed_tag_as_released():
    """`v0.3.0` predates the `server-v` prefix, so the job does not release 0.3.0 again (#145)."""
    assert 'gh release view "v$version"' in run_lines(release_workflow())


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

    assert 'tag="server-v$version"' in scripts
    assert 'gh release view "$tag"' in scripts
    assert "server/pyproject.toml" in scripts
    assert "server/CHANGELOG.md" in scripts
    assert 'gh release create "$tag"' in scripts
    assert '--target "$GITHUB_SHA"' in scripts


def qa_job_steps() -> list[dict[str, Any]]:
    """The steps of the CI `qa` job, in order."""
    return load(ROOT / ".github/workflows/server.yml")["jobs"]["qa"]["steps"]


def test_ci_has_no_css_build_step():
    """The stylesheets are served as written, so CI builds no CSS before QA."""
    runs = [step.get("run", "") for step in qa_job_steps()]

    assert "make css" not in runs
    assert "make qa" in runs


PR_TITLE = ROOT / ".github/workflows/pr-title.yml"


def test_pr_titles_are_linted_when_opened_or_edited():
    """The PR title becomes the squash-merge subject, so CI checks it on every change (#68)."""
    on = triggers(PR_TITLE)

    assert set(on) == {"pull_request"}
    assert {"opened", "edited", "reopened", "synchronize"} <= set(on["pull_request"]["types"])


def test_pr_title_is_checked_with_commitizen_from_the_environment():
    """`cz check` lints the title, passed through `env` so it is never spliced into the script."""
    workflow = load(PR_TITLE)
    (step,) = [step for step in steps(workflow) if "cz check" in step.get("run", "")]

    assert step["env"]["PR_TITLE"] == "${{ github.event.pull_request.title }}"
    assert 'cz check --message "$PR_TITLE"' in step["run"]
    assert "--directory server" in step["run"]
    assert "github.event" not in step["run"]


def e2e_job() -> dict[str, Any]:
    """`server.yml` cut down to its browser-test job."""
    return {"jobs": {"e2e": load(ROOT / ".github/workflows/server.yml")["jobs"]["e2e"]}}


def test_ci_runs_the_browser_tests_in_chromium():
    """A separate job installs the locked Playwright's Chromium, then runs `make e2e` (#63)."""
    runs = [step.get("run", "") for step in steps(e2e_job())]

    install = runs.index("uv sync --locked --all-groups")
    chromium = runs.index("uv run playwright install --only-shell chromium")
    e2e = next(i for i, run in enumerate(runs) if run.startswith("make e2e"))
    assert install < chromium < e2e


def test_ci_keeps_screenshots_of_failed_browser_tests():
    """A failed browser test leaves a screenshot in an uploaded artifact."""
    job = e2e_job()
    (upload,) = steps_using(job, "actions/upload-artifact")

    assert "--screenshot only-on-failure" in run_lines(job)
    assert upload["if"] == "failure()"
    assert upload["with"]["path"] == "server/test-results/"
