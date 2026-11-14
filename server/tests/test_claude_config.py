"""Tests for the committed Claude Code configuration under `.claude/` (#70)."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # the repository; the server is ROOT / "server"
CLAUDE = ROOT / ".claude"
SETTINGS = json.loads((CLAUDE / "settings.json").read_text())
HOOKS = CLAUDE / "hooks"
AGENTS = (ROOT / "AGENTS.md").read_text()
FEATURES = ROOT / "server" / "docs" / "features"


def hook_commands(settings: dict) -> list[str]:
    """Every hook command a settings file registers, across all events."""
    return [
        hook["command"]
        for groups in settings.get("hooks", {}).values()
        for group in groups
        for hook in group["hooks"]
    ]


def session_start_groups(command_part: str) -> list[dict]:
    """The SessionStart groups whose hooks run a command containing `command_part`."""
    return [
        group
        for group in SETTINGS["hooks"]["SessionStart"]
        if any(command_part in hook["command"] for hook in group["hooks"])
    ]


def test_caveman_mode_is_on_for_every_session():
    """Caveman mode, its per-prompt tracker and its status line are wired in the shared settings."""
    commands = hook_commands(SETTINGS)

    assert any("caveman-activate.sh" in command for command in commands)
    assert any("caveman-mode-tracker.sh" in command for command in commands)
    assert "caveman-statusline.sh" in SETTINGS["statusLine"]["command"]


def test_caveman_is_reinjected_after_compaction():
    """The caveman rules come back after a compaction, so the mode does not drift."""
    (group,) = session_start_groups("caveman-activate.sh")

    assert group.get("matcher", "*") == "*"


def test_branch_hook_fires_on_startup_only():
    """A `*` matcher would re-ask for the branch after every compaction and stall headless runs."""
    (group,) = session_start_groups("branch")

    assert group["matcher"] == "startup"


def test_branch_hook_does_not_block_non_interactive_runs():
    """The branch reminder tells a headless run to carry on rather than wait for an answer."""
    (group,) = session_start_groups("branch")

    assert "non-interactive" in group["hooks"][0]["command"]


def test_hook_scripts_run_through_the_project_dir():
    """Hooks run by absolute path, so they work when the shell is in `src/` or `tests/`."""
    commands = [*hook_commands(SETTINGS), SETTINGS["statusLine"]["command"]]

    for command in [c for c in commands if ".claude/hooks/" in c]:
        script = re.search(r'"\$CLAUDE_PROJECT_DIR"/(\.claude/hooks/\S+\.sh)', command)
        assert script is not None, command
        assert (ROOT / script.group(1)).exists()


@pytest.mark.parametrize(
    "rule",
    [
        "Bash(make qa)",
        "Bash(make test *)",
        "Bash(make test-cov)",
        "Bash(make test-cov *)",
        "Bash(uv run pytest *)",
        "Bash(uv run ruff *)",
        "Bash(uv run ty *)",
        "Bash(git status *)",
        "Bash(git diff *)",
        "Bash(git log *)",
    ],
)
def test_mandated_commands_are_allowed_without_a_prompt(rule: str):
    """The commands AGENTS.md requires run without a permission prompt."""
    assert rule in SETTINGS["permissions"]["allow"]


def test_local_settings_are_git_ignored():
    """Personal overrides of the shared settings never get committed."""
    ignored = (ROOT / ".gitignore").read_text().splitlines()

    assert ".claude/settings.local.json" in ignored


def test_every_skill_is_discoverable():
    """Claude Code only finds skills laid out as `.claude/skills/<name>/SKILL.md`."""
    skills = CLAUDE / "skills"

    assert not list(skills.glob("*.md"))
    for directory in skills.iterdir():
        assert (directory / "SKILL.md").exists(), directory.name


def test_agents_md_points_at_the_tdd_skill():
    """AGENTS.md references the TDD skill where Claude Code discovers it."""
    assert (CLAUDE / "skills" / "tdd" / "SKILL.md").exists()
    assert ".claude/skills/tdd/SKILL.md" in AGENTS


def test_caveman_patterns_live_in_one_place():
    """The regression test checks the tracker's own patterns, not a copy of them."""
    config = (HOOKS / "caveman-config.sh").read_text()
    names = ("CAVEMAN_ACTIVATE_RE", "CAVEMAN_NEGATE_RE", "CAVEMAN_DEACTIVATE_RE")

    for name in names:
        assert f"{name}=" in config
        for script in ("caveman-mode-tracker.sh", "test-caveman-patterns.sh"):
            text = (HOOKS / script).read_text()
            assert f"${name}" in text
            assert f"{name}=" not in text


def test_caveman_mode_leaves_docs_in_full_prose():
    """Docs are user-facing, so caveman mode writes them normally."""
    # The hook's fallback text sits in a heredoc, so its backticks are escaped.
    for text in (
        (CLAUDE / "skills" / "caveman" / "SKILL.md").read_text(),
        (HOOKS / "caveman-activate.sh").read_text().replace("\\`", "`"),
    ):
        assert "Code/commits/PRs/docs (`*.md`): write normal." in text


def test_initial_context_is_gone():
    """AGENTS.md carries the architecture summary; nothing points at the old file."""
    assert not (ROOT / "docs" / "initial-context.md").exists()
    for doc in (ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "docs" / "developer-guide.md"):
        assert "initial-context" not in doc.read_text(), doc.name


def test_agents_md_indexes_every_feature_note():
    """Each note in `docs/features/` is listed in AGENTS.md, and each listed note exists."""
    listed = set(re.findall(r"docs/features/([\w-]+\.md)", AGENTS))
    present = {path.name for path in FEATURES.glob("*.md")}

    assert listed
    assert listed == present
