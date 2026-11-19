"""Tests for the git hooks in `.pre-commit-config.yaml` (#68)."""

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]  # the repository; the server is ROOT / "server"
CONFIG = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())


def local_hook(hook_id: str) -> dict[str, Any]:
    """The hook with `hook_id` from the `local` repo."""
    (repo,) = [repo for repo in CONFIG["repos"] if repo["repo"] == "local"]
    (hook,) = [hook for hook in repo["hooks"] if hook["id"] == hook_id]
    return hook


def test_commit_messages_are_checked_through_uv():
    """The commitizen hook uses the server's tools, from the repository root (#145).

    `--project` rather than `--directory`: git passes the message file relative to the root.
    """
    hook = local_hook("commitizen")

    assert hook["entry"] == "uv run --project server --frozen cz check"
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


def test_extension_changes_run_the_extension_checks():
    """A commit under `extension/` runs `make ext-qa`, once, whatever files it touches."""
    hook = local_hook("ext-qa")

    assert hook["entry"] == "make ext-qa"
    assert hook["files"] == "^extension/"
    assert hook["pass_filenames"] is False


def test_a_change_to_the_tdd_hook_runs_its_tests():
    """The agents' TDD hook has its own regression tests, run when it changes."""
    hook = local_hook("tdd-hook-tests")

    assert hook["entry"] == "bash .claude/hooks/test-check-tdd.sh"
    assert hook["files"] == r"^\.claude/hooks/(test-)?check-tdd\.sh$"
    assert hook["pass_filenames"] is False
