"""Tests for the server's release setup: one version number, cut by commitizen (#72, #145)."""

import tomllib
from pathlib import Path

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
