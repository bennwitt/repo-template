from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _no_machine_config_dirs(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test that points HOME at a temporary folder makes it this machine's home to the code,
    which then honors CODEX_HOME and CLAUDE_CONFIG_DIR: never let those reach the real ones."""
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


@pytest.fixture(autouse=True)
def _no_git_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run from a pre-commit hook (in a worktree above all), Git sets GIT_DIR and
    GIT_INDEX_FILE, and `git -c` sets GIT_CONFIG_PARAMETERS; a test's `git -C <tmp> ...` would
    then write to this repository, or see its settings. Tests run with no GIT_* variable."""
    for name in list(os.environ):
        if name.startswith("GIT_") and name != "GIT_EDITOR":
            monkeypatch.delenv(name, raising=False)
