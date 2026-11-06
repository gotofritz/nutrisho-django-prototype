"""Tests for the committed Claude Code configuration under `.claude/` (#70)."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = ROOT / ".claude"
SETTINGS = json.loads((CLAUDE / "settings.json").read_text())
LOCAL_EXAMPLE = CLAUDE / "settings.local.example.json"
HOOKS = CLAUDE / "hooks"
AGENTS = (ROOT / "AGENTS.md").read_text()


def hook_commands(settings: dict) -> list[str]:
    """Every hook command a settings file registers, across all events."""
    return [
        hook["command"]
        for groups in settings.get("hooks", {}).values()
        for group in groups
        for hook in group["hooks"]
    ]


def test_shared_settings_leave_output_style_and_status_line_alone():
    """Caveman mode and its status line are opt-in, never forced on every contributor."""
    assert "statusLine" not in SETTINGS
    assert not [command for command in hook_commands(SETTINGS) if "caveman" in command]


def test_session_start_hooks_fire_on_startup_only():
    """A `*` matcher would re-fire after every compaction and stall headless runs."""
    matchers = [group.get("matcher") for group in SETTINGS["hooks"]["SessionStart"]]

    assert matchers == ["startup"]


def test_branch_hook_does_not_block_non_interactive_runs():
    """The branch reminder tells a headless run to carry on rather than wait for an answer."""
    (command,) = hook_commands(SETTINGS)

    assert "non-interactive" in command


@pytest.mark.parametrize(
    "rule",
    [
        "Bash(make qa)",
        "Bash(make test *)",
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


def test_local_example_wires_caveman_through_the_project_dir():
    """The opt-in example runs hooks by absolute path, so they work from any directory."""
    example = json.loads(LOCAL_EXAMPLE.read_text())
    commands = [*hook_commands(example), example["statusLine"]["command"]]

    assert commands
    for command in commands:
        assert '"$CLAUDE_PROJECT_DIR"/.claude/hooks/' in command
        assert (ROOT / re.search(r"\.claude/hooks/\S+\.sh", command).group()).exists()


def test_local_settings_are_git_ignored():
    """Personal settings, such as the caveman hooks, never get committed."""
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

