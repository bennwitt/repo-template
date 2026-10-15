from __future__ import annotations

import os

import pytest

from repo_template import repository


@pytest.fixture(autouse=True)
def _no_real_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    """A personal adoption adds servers to Claude Code's local scope through the real `claude`
    CLI and ~/.claude.json: a test passes a fake (and a temporary home) or gets none."""
    monkeypatch.setattr(repository, "local_claude", lambda root, home: None)


@pytest.fixture(autouse=True)
def _no_machine_config_dirs(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test that points HOME at a temporary folder makes it this machine's home to the code,
    which then honors CODEX_HOME, CLAUDE_CONFIG_DIR and XDG_CONFIG_HOME: never let those reach
    the real ones."""
    for name in ("CODEX_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_git_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run from a pre-commit hook (in a worktree above all), Git sets GIT_DIR and
    GIT_INDEX_FILE, and `git -c` sets GIT_CONFIG_PARAMETERS; a test's `git -C <tmp> ...` would
    then write to this repository, or see its settings. Tests run with no GIT_* variable, and
    without the system config (whose core.excludesFile globals would otherwise write to)."""
    for name in list(os.environ):
        if name.startswith("GIT_") and name != "GIT_EDITOR":
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
