"""Guards against the documentation drifting from the code and from AGENTS.md (#69)."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # the repository; the server is ROOT / "server"
AGENTS = (ROOT / "AGENTS.md").read_text()
DEVELOPER_GUIDE = (ROOT / "docs" / "developer-guide.md").read_text()
PYPROJECT = tomllib.loads((ROOT / "server" / "pyproject.toml").read_text())


def section(text: str, heading: str) -> str:
    """The body of the Markdown section under `heading`, up to the next heading."""
    match = re.search(rf"^{re.escape(heading)}\n(.*?)(?=^#)", text, flags=re.M | re.S)
    assert match is not None, heading
    return match.group(1)


def declared_packages() -> set[str]:
    """Every runtime and dev dependency in pyproject.toml, by normalised name."""
    specs = [*PYPROJECT["project"]["dependencies"], *PYPROJECT["dependency-groups"]["dev"]]
    return {re.split(r"[\s<>=~!;\[]", spec, maxsplit=1)[0].lower() for spec in specs}


def test_agents_md_names_only_installed_libraries():
    """A library AGENTS.md tells agents to use is one the project actually depends on."""
    named = set()
    for heading in ("### Tooling", "### Libraries", "### Testing"):
        named |= set(re.findall(r"`([a-z][a-z0-9-]*)`", section(AGENTS, heading)))

    assert named
    assert named - {"uv"} <= declared_packages()


def test_developer_guide_follows_the_agents_md_branch_format():
    """The retired `feature/<name>` form is gone; the guide points at AGENTS.md instead."""
    assert "feature/<name>" not in DEVELOPER_GUIDE
    assert "AGENTS.md#branches" in DEVELOPER_GUIDE


def test_package_metadata_has_no_placeholders():
    """The wheel's metadata describes this project and its author."""
    project = PYPROJECT["project"]

    assert "quick and dirty" not in project["description"].lower()
    for author in project["authors"]:
        assert author["name"] != "Your Name"
        assert not author.get("email", "").endswith("@example.com")


def test_first_time_setup_installs_the_git_hooks():
    """Setup installs pre-commit, so commit messages are checked before they reach CI (#68)."""
    # Not `section()`: the setup code block holds a `# ...` shell comment.
    setup = DEVELOPER_GUIDE.split("## First-time setup\n")[1].split("\n## ")[0]

    assert "pre-commit install" in setup
    assert "pnpm install\n" not in setup


def test_quality_checks_document_both_test_targets():
    """The guide says which test target is the fast loop and which is the coverage gate."""
    checks = section(DEVELOPER_GUIDE, "## Quality checks")

    assert "make test " in checks
    assert "make test-cov" in checks
    assert "CSS build" not in checks
