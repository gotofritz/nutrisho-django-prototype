"""Tests for project-wide invariants that coverage and pytest rely on."""

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())
# Every directory between src/ and a .py file, so a package-less parent is caught too.
SOURCE_DIRS = sorted(
    {parent for path in SRC.rglob("*.py") for parent in path.parents if SRC in parent.parents}
)


@pytest.mark.parametrize("directory", SOURCE_DIRS, ids=lambda path: str(path.relative_to(SRC)))
def test_every_source_directory_is_a_package(directory: Path):
    """Coverage only reports files in packages, so an untested module can't hide."""
    assert (directory / "__init__.py").exists()


def test_coverage_measures_branches():
    """Coverage counts untaken branches, not just unrun lines."""
    assert PYPROJECT["tool"]["coverage"]["run"]["branch"] is True


def test_pytest_fails_on_undefined_template_variables():
    """An undefined template variable fails the test instead of rendering empty."""
    assert "--fail-on-template-vars" in PYPROJECT["tool"]["pytest"]["ini_options"]["addopts"]


def test_the_default_run_skips_the_browser_tests():
    """Browser tests need Chromium and the built CSS, so plain pytest and `make qa` skip them (#63)."""
    pytest_options = PYPROJECT["tool"]["pytest"]["ini_options"]
    addopts = pytest_options["addopts"]

    assert addopts[addopts.index("-m") + 1] == "not e2e"
    assert any(marker.startswith("e2e:") for marker in pytest_options["markers"])


REPO = ROOT.parent


def test_the_repository_holds_the_server_and_the_extension_side_by_side():
    """The Django app is self-contained under `server/`; `extension/` waits for the clipper (#145)."""
    for name in ("pyproject.toml", "uv.lock", "manage.py", "CHANGELOG.md"):
        assert (ROOT / name).exists(), name
        assert not (REPO / name).exists(), name
    assert (REPO / "extension" / "README.md").exists()


def test_database_dumps_stay_out_of_git():
    """`make backup` writes its dumps to `server/docs/`, which the root .gitignore covers."""
    assert "server/docs/dump-*" in (REPO / ".gitignore").read_text().splitlines()
