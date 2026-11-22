"""Tests for the server's release setup: one version number, cut by commitizen (#72, #145)."""

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())
COMMITIZEN = PYPROJECT["tool"]["commitizen"]
CHANGELOG = ROOT / "CHANGELOG.md"


def test_commitizen_keeps_the_version_in_pyproject_and_uv_lock():
    """`cz bump` writes the version to pyproject.toml and uv.lock, so `uv sync --locked` holds."""
    assert COMMITIZEN["version_provider"] == "uv"


def test_server_releases_are_tagged_with_a_server_prefix():
    """The server and the extension release separately: server 0.4.0 is tagged `server-v0.4.0`."""
    assert COMMITIZEN["tag_format"] == "server-v$version"


def test_the_unprefixed_tags_still_count_as_server_releases():
    """`v0.3.0` predates the prefix, so `cz bump` still finds it as the last server release."""
    assert COMMITIZEN["legacy_tag_formats"] == ["v$version"]


def test_extension_tags_are_not_server_releases():
    """`cz bump` in the server never mistakes an `ext-v*` tag for its own."""
    assert COMMITIZEN["ignored_tag_formats"] == ["ext-v*"]


def test_bumping_updates_the_changelog():
    """Every `cz bump` adds the new version's section to CHANGELOG.md."""
    assert COMMITIZEN["update_changelog_on_bump"] is True


def test_breaking_changes_stay_below_1_0():
    """A breaking change bumps the minor version until the project chooses to reach 1.0."""
    assert COMMITIZEN["major_version_zero"] is True


def test_uv_lock_agrees_with_the_project_version():
    """The lockfile's own entry for nutrisho carries the pyproject.toml version."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    (entry,) = [package for package in lock["package"] if package["name"] == "nutrisho"]

    assert entry["version"] == PYPROJECT["project"]["version"]


def test_changelog_has_a_section_for_the_current_version():
    """The version in pyproject.toml was cut with `cz bump`, which wrote its CHANGELOG.md section."""
    version = PYPROJECT["project"]["version"]
    headings = (f"## server-v{version} (", f"## v{version} (")  # v0.3.0 predates the prefix

    assert any(line.startswith(headings) for line in CHANGELOG.read_text().splitlines())


SERVER_COMMITS = ["feat: add a tool", "fix(export): keep the singular", "perf!: drop a query"]
EXTENSION_COMMITS = [
    "feat(ext): clip a recipe",
    "fix(ext): say the error",
    "feat(ext)!: change the draft",
]


def _patterns() -> dict[str, re.Pattern[str]]:
    """What commitizen matches a subject against to bump, list and parse it."""
    customize = COMMITIZEN["customize"]
    return {
        name: re.compile(customize[name])
        for name in ("bump_pattern", "changelog_pattern", "commit_parser")
    }


@pytest.mark.parametrize("message", SERVER_COMMITS)
def test_server_commits_count_towards_a_server_release(message: str):
    """A server commit, scoped or not, bumps the version and has a changelog line."""
    assert all(pattern.match(message) for pattern in _patterns().values())


@pytest.mark.parametrize("message", EXTENSION_COMMITS)
def test_extension_commits_are_left_out(message: str):
    """A commit scoped `ext` counts for the extension's release (M15), never the server's."""
    assert not any(pattern.match(message) for pattern in _patterns().values())
