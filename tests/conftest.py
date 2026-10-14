from __future__ import annotations

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
    GIT_INDEX_FILE; a test's `git -C <tmp> ...` would then commit to this repository."""
    for name in (
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_WORK_TREE",
        "GIT_PREFIX",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        monkeypatch.delenv(name, raising=False)
