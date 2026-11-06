"""Tests for the release setup: one version number, cut by commitizen (#72)."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())
COMMITIZEN = PYPROJECT["tool"]["commitizen"]


def test_commitizen_keeps_the_version_in_pyproject_and_uv_lock():
    """`cz bump` writes the version to pyproject.toml and uv.lock, so `uv sync --locked` holds."""
    assert COMMITIZEN["version_provider"] == "uv"


def test_releases_are_tagged_with_a_v_prefix():
    """Version 0.3.0 is tagged `v0.3.0`."""
    assert COMMITIZEN["tag_format"] == "v$version"


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


def test_package_json_has_no_version_of_its_own():
    """pyproject.toml holds the only version number; package.json is private tooling."""
    package = json.loads((ROOT / "package.json").read_text())

    assert package["private"] is True
    assert "version" not in package
