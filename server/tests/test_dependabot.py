"""Tests for the Dependabot configuration that keeps dependencies up to date."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]  # the repository; the server is ROOT / "server"
CONFIG = ROOT / ".github" / "dependabot.yml"


@pytest.mark.parametrize("ecosystem", ["uv", "github-actions", "pre-commit"])
def test_every_ecosystem_gets_updates(ecosystem: str):
    """Each ecosystem the project depends on has a Dependabot update entry."""
    entries = re.findall(r"package-ecosystem:\s*([\w-]+)", CONFIG.read_text())

    assert ecosystem in entries


@pytest.mark.parametrize(
    ("ecosystem", "directory"),
    [("uv", "/server"), ("github-actions", "/"), ("pre-commit", "/")],
)
def test_each_ecosystem_is_watched_where_its_files_live(ecosystem: str, directory: str):
    """The server's lockfile is under `server/`; workflows and hooks are repo-wide (#145)."""
    entries = yaml.safe_load(CONFIG.read_text())["updates"]

    assert {"package-ecosystem": ecosystem, "directory": directory}.items() <= next(
        entry for entry in entries if entry["package-ecosystem"] == ecosystem
    ).items()


def test_no_npm_updates_until_the_extension_has_a_package_json():
    """Dependabot errors on a directory without a manifest, so npm waits for `extension/package.json`."""
    has_npm = "package-ecosystem: npm" in CONFIG.read_text()

    assert has_npm == (ROOT / "extension" / "package.json").exists()
