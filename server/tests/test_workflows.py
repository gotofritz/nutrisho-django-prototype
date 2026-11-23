"""Tests for the GitHub Actions workflows: token scope, pinning and run limits."""

import json
import os
import re
import shutil
import subprocess
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
            assert name in {"badge", "release", "ext-release", "ext-sign"}
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


EXTENSION_WORKFLOW = ROOT / ".github/workflows/extension.yml"


@pytest.mark.parametrize(
    "path", [p for p in WORKFLOWS if p != EXTENSION_WORKFLOW], ids=lambda path: path.name
)
def test_only_the_extension_workflow_sets_up_node(path: Path):
    """The server has no Node toolchain since Tailwind went, so only the extension's jobs use pnpm."""
    assert not steps_using(load(path), "pnpm/action-setup")
    assert not steps_using(load(path), "actions/setup-node")
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


GATED_WORKFLOWS = [*SERVER_WORKFLOWS, EXTENSION_WORKFLOW]


@pytest.mark.parametrize("path", GATED_WORKFLOWS, ids=lambda path: path.name)
def test_every_push_and_pull_request_runs_the_workflow(path: Path):
    """No path filter on the triggers, so the workflow always reports (#145).

    A workflow a path filter skips never reports, and a required check would wait
    for it for ever. Each job decides for itself instead.
    """
    for event in ("push", "pull_request"):
        assert not {"paths", "paths-ignore"} & set(triggers(path)[event] or {})


@pytest.mark.parametrize("path", GATED_WORKFLOWS, ids=lambda path: path.name)
def test_every_job_waits_for_the_changes_job(path: Path):
    """The checks run only when `changes` says so; a job skipped by its condition counts as passed."""
    jobs = load(path)["jobs"]
    (output,) = jobs["changes"]["outputs"]

    for name, job in jobs.items():
        if name == "changes":
            continue
        if job["needs"] == "changes":
            assert job["if"] == f"needs.changes.outputs.{output} == 'true'", name
        else:
            # The badge and release jobs follow qa, and qa follows changes;
            # the extension's signing follows its release.
            before = job["needs"]
            while jobs[before]["needs"] != "changes":
                before = jobs[before]["needs"]
            assert before != name


def changes_step(path: Path) -> dict[str, Any]:
    """The step of a workflow's `changes` job that decides whether the checks run."""
    (step,) = [s for s in load(path)["jobs"]["changes"]["steps"] if s.get("id") == "diff"]
    return step


def git(repo: Path, *args: str) -> str:
    """Run git in `repo` as a throwaway committer and return its output."""
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def decide(path: Path, changed: list[str], tmp_path: Path, *, base: str | None = "parent") -> str:
    """What the `changes` job of workflow `path` answers for a commit that touches `changed`.

    `base` is the commit before the change; None is a run with no base (a schedule, a
    manual run), and any other text is a commit the clone does not have (a force push).
    """
    repo = tmp_path / "repo"
    (repo / ".github" / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPTS / "touches.sh", repo / ".github" / "scripts" / "touches.sh")
    git(repo, "init", "--quiet")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "base")
    parent = git(repo, "rev-parse", "HEAD")
    for name in changed:
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        with (repo / name).open("a") as file:  # appended, so the script itself still runs
            file.write("\n# changed\n")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "change")

    output = tmp_path / "output"
    output.write_text("")
    env = {
        "PATH": os.environ["PATH"],
        "GITHUB_OUTPUT": str(output),
        "GITHUB_SHA": git(repo, "rev-parse", "HEAD"),
        "BASE": {"parent": parent, None: ""}.get(base, base or ""),
    }
    subprocess.run(["bash", "-c", changes_step(path)["run"]], cwd=repo, env=env, check=True)
    ((key, value),) = [line.split("=", 1) for line in output.read_text().splitlines()]
    (name,) = load(path)["jobs"]["changes"]["outputs"]
    assert key == name
    return value


SCRIPTS = ROOT / ".github" / "scripts"
SERVER = ROOT / ".github/workflows/server.yml"
AUDIT = ROOT / ".github/workflows/server-audit.yml"


@pytest.mark.parametrize(
    ("path", "changed", "runs"),
    [
        (SERVER, ["extension/src/clip.ts"], "false"),
        (SERVER, ["extension/package.json", "extension/README.md"], "false"),
        (SERVER, ["server/src/recipes/models.py"], "true"),
        (SERVER, ["extension/src/clip.ts", "AGENTS.md"], "true"),
        (SERVER, [".github/workflows/extension.yml"], "true"),
        (AUDIT, ["extension/src/clip.ts"], "false"),
        (AUDIT, ["server/uv.lock"], "true"),
        (EXTENSION_WORKFLOW, ["server/src/recipes/models.py"], "false"),
        (EXTENSION_WORKFLOW, ["docs/plans/012-recipe-clipper.md"], "false"),
        (EXTENSION_WORKFLOW, ["extension/src/clip.ts"], "true"),
        (EXTENSION_WORKFLOW, [".github/workflows/extension.yml"], "true"),
        (EXTENSION_WORKFLOW, [".github/scripts/touches.sh"], "true"),
        (EXTENSION_WORKFLOW, ["Makefile"], "true"),
        (EXTENSION_WORKFLOW, [".pre-commit-config.yaml"], "true"),
        (EXTENSION_WORKFLOW, ["server/tests/api_examples/save.json"], "true"),
        (EXTENSION_WORKFLOW, ["server/src/recipes/static/css/style.css"], "true"),
        (EXTENSION_WORKFLOW, ["server/src/recipes/static/fonts/lobster/OFL.txt"], "true"),
        (EXTENSION_WORKFLOW, ["server/src/recipes/static/img/plate-lineout.webp"], "true"),
        (EXTENSION_WORKFLOW, ["server/src/recipes/static/js/app.js"], "false"),
    ],
    ids=lambda value: value.name if isinstance(value, Path) else None,
)
def test_the_checks_run_for_the_files_they_cover(
    path: Path, changed: list[str], runs: str, tmp_path: Path
):
    """Each part's checks run for the files they concern (#145).

    The server skips extension-only changes; the extension runs for its own files,
    its workflow, the Makefile, the hooks, the API examples its tests read and the
    site's stylesheet, fonts and plate it copies.
    """
    assert decide(path, changed, tmp_path) == runs


@pytest.mark.parametrize("path", GATED_WORKFLOWS, ids=lambda path: path.name)
@pytest.mark.parametrize("base", [None, "0" * 40], ids=["no base", "unknown base"])
def test_everything_runs_when_there_is_nothing_to_compare_with(
    path: Path, base: str | None, tmp_path: Path
):
    """A schedule, a manual run, a new branch or a force push runs every check."""
    assert decide(path, ["nothing/in/particular.txt"], tmp_path, base=base) == "true"


@pytest.mark.parametrize("path", GATED_WORKFLOWS, ids=lambda path: path.name)
def test_the_changes_job_compares_with_the_base_of_the_pull_request_or_push(path: Path):
    """The whole history is fetched, so the base commit is there to diff against."""
    job = load(path)["jobs"]["changes"]
    (checkout,) = steps_using({"jobs": {"changes": job}}, "actions/checkout")

    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["persist-credentials"] is False
    assert changes_step(path)["env"]["BASE"] == (
        "${{ github.event.pull_request.base.sha || github.event.before }}"
    )


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


def extension_job() -> dict[str, Any]:
    """`extension.yml` cut down to its checks job."""
    return {"jobs": {"ext-qa": load(EXTENSION_WORKFLOW)["jobs"]["ext-qa"]}}


def test_each_check_has_a_name_of_its_own():
    """A required check is named by its job, so the extension's is not a second `qa`."""
    names = [name for path in WORKFLOWS for name in load(path)["jobs"] if name != "changes"]

    assert len(names) == len(set(names))


def ext_release_workflow() -> dict[str, Any]:
    """`extension.yml` cut down to its release job (M15)."""
    return {"jobs": {"ext-release": load(EXTENSION_WORKFLOW)["jobs"]["ext-release"]}}


def test_the_extension_zips_are_built_by_the_checks_on_main():
    """The zips come from the read-only checks job, only on a push to main, for the release to take."""
    zip_step, upload = [
        step
        for step in steps(extension_job())
        if step.get("run") == "make ext-zip"
        or step.get("uses", "").startswith("actions/upload-artifact@")
    ]

    assert "github.ref == 'refs/heads/main'" in zip_step["if"]
    assert "github.event_name == 'push'" in zip_step["if"]
    assert upload["if"] == zip_step["if"]
    assert upload["with"]["path"] == "extension/.output/*.zip"


def test_ext_release_job_runs_only_after_the_checks_pass_on_main():
    """An extension version is released only from a green push to main (M15)."""
    release = ext_release_workflow()["jobs"]["ext-release"]

    assert release["needs"] == "ext-qa"
    assert "needs.ext-qa.result == 'success'" in release["if"]
    assert "github.event_name == 'push'" in release["if"]
    assert "github.ref == 'refs/heads/main'" in release["if"]


def test_ext_release_job_runs_no_project_code():
    """The write-scoped job checks out without saved credentials, takes the zips, and runs only gh."""
    workflow = ext_release_workflow()
    (checkout,) = steps_using(workflow, "actions/checkout")
    scripts = run_lines(workflow)

    assert checkout["with"]["persist-credentials"] is False
    assert steps_using(workflow, "actions/download-artifact")
    for command in ("uv ", "make ", "pnpm ", "python", "node "):
        assert command not in scripts


def test_ext_release_job_publishes_the_changelog_section_for_a_new_tag():
    """It tags `ext-v<version>` once, from package.json, with its CHANGELOG.md section as notes."""
    scripts = run_lines(ext_release_workflow())

    assert 'tag="ext-v$version"' in scripts
    assert "extension/package.json" in scripts
    assert "extension/CHANGELOG.md" in scripts
    assert 'gh release view "$tag"' in scripts
    assert 'gh release create "$tag"' in scripts
    assert '--target "$GITHUB_SHA"' in scripts
    assert "--latest=false" in scripts


def ext_sign_job() -> dict[str, Any]:
    """`extension.yml`'s job that has AMO sign the Firefox build (M15)."""
    return load(EXTENSION_WORKFLOW)["jobs"]["ext-sign"]


def test_ext_release_job_names_the_tag_it_made():
    """The signing job runs only for a release just made, which it learns from this output."""
    release = ext_release_workflow()["jobs"]["ext-release"]

    assert release["outputs"] == {"tag": "${{ steps.publish.outputs.tag }}"}
    assert 'echo "tag=$tag" >> "$GITHUB_OUTPUT"' in run_lines(ext_release_workflow())


def test_ext_sign_job_runs_only_for_a_new_release_with_a_reviewer():
    """Signing follows a new release, in the environment whose reviewer lets it run (#145)."""
    job = ext_sign_job()

    assert job["needs"] == "ext-release"
    assert job["if"] == "needs.ext-release.outputs.tag != ''"
    assert job["environment"] == "store-publishing"


def test_ext_sign_job_signs_unlisted_with_the_pinned_web_ext():
    """AMO signs the zip the checks built, as unlisted (D22), with the web-ext the project pins."""
    package = json.loads((ROOT / "extension" / "package.json").read_text())
    scripts = run_lines({"jobs": {"ext-sign": ext_sign_job()}})

    assert f"npx --yes web-ext@{package['devDependencies']['web-ext']} sign" in scripts
    assert "--channel unlisted" in scripts
    assert "--upload-source-code" in scripts
    assert 'gh release upload "$TAG"' in scripts


def test_ext_sign_job_reads_the_amo_keys_from_its_environment_only():
    """The keys are the environment's secrets, given to the signing step alone, never echoed."""
    job = ext_sign_job()
    (sign,) = [step for step in job["steps"] if "web-ext" in step.get("run", "")]

    assert sign["env"]["WEB_EXT_API_KEY"] == "${{ secrets.AMO_API_KEY }}"
    assert sign["env"]["WEB_EXT_API_SECRET"] == "${{ secrets.AMO_API_SECRET }}"
    assert "env" not in job
    assert 'echo "$WEB_EXT' not in sign["run"]


def test_ext_sign_job_runs_no_project_code():
    """With the AMO keys in reach, the job checks out without credentials and installs nothing of ours."""
    workflow = {"jobs": {"ext-sign": ext_sign_job()}}
    (checkout,) = steps_using(workflow, "actions/checkout")
    scripts = run_lines(workflow)

    assert checkout["with"]["persist-credentials"] is False
    for command in ("uv ", "make ", "pnpm ", "python"):
        assert command not in scripts


def test_ext_sign_job_tells_firefox_where_the_new_version_is():
    """`updates.json` on the `ext-updates` branch is what the manifest's `update_url` names."""
    workflow = {"jobs": {"ext-sign": ext_sign_job()}}
    (publish,) = steps_using(workflow, "peaceiris/actions-gh-pages")
    scripts = run_lines(workflow)

    assert publish["with"]["publish_branch"] == "ext-updates"
    assert "nutrisho-clipper@gotofritz.net" in scripts
    assert "update_link" in scripts


def test_the_extension_checks_run_through_make():
    """CI installs from the lockfile and runs the same `make ext-qa` as a developer does."""
    runs = [step.get("run", "") for step in steps(extension_job())]

    assert runs.index("make ext-install") < runs.index("make ext-qa")


def test_the_extension_uses_the_node_and_pnpm_it_pins():
    """Node comes from `extension/.nvmrc` and pnpm from `packageManager` in its package.json."""
    job = extension_job()
    (pnpm,) = steps_using(job, "pnpm/action-setup")
    (node,) = steps_using(job, "actions/setup-node")

    assert pnpm["with"] == {"package_json_file": "extension/package.json"}
    assert node["with"]["node-version-file"] == "extension/.nvmrc"
    assert node["with"]["cache-dependency-path"] == "extension/pnpm-lock.yaml"
