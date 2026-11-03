"""Tests for the Dependabot configuration that keeps dependencies up to date."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".github" / "dependabot.yml"


@pytest.mark.parametrize("ecosystem", ["uv", "npm", "github-actions", "pre-commit"])
def test_every_ecosystem_gets_updates(ecosystem: str):
    """Each ecosystem the project depends on has a Dependabot update entry."""
    entries = re.findall(r"package-ecosystem:\s*([\w-]+)", CONFIG.read_text())

    assert ecosystem in entries
