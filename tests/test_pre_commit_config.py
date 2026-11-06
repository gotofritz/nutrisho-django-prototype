"""Tests for the git hooks in `.pre-commit-config.yaml` (#68)."""

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())


def local_hook(hook_id: str) -> dict[str, Any]:
    """The hook with `hook_id` from the `local` repo."""
    (repo,) = [repo for repo in CONFIG["repos"] if repo["repo"] == "local"]
    (hook,) = [hook for hook in repo["hooks"] if hook["id"] == hook_id]
    return hook


def test_commit_messages_are_checked_through_uv():
    """The commitizen hook works without a `.venv` at a fixed path."""
    hook = local_hook("commitizen")

    assert hook["entry"] == "uv run --frozen cz check"
    assert hook["stages"] == ["commit-msg"]


def test_qa_hook_runs_make_qa_frozen():
    """`make qa` from the hook installs from uv.lock without re-resolving it.

    A hook that rewrites uv.lock aborts the commit or rebase it runs in, and a global
    `UV_EXCLUDE_NEWER` that differs from the lock's recorded setting makes a plain
    `uv run` re-resolve.
    """
    assert local_hook("qa")["entry"] == "env UV_FROZEN=1 make qa"


def test_commit_msg_hooks_are_installed_by_default():
    """`pre-commit install` alone installs the commit-msg stage the commitizen hook runs in."""
    assert "commit-msg" in CONFIG["default_install_hook_types"]
