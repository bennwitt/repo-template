from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_machine_config_dirs(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test that points HOME at a temporary folder makes it this machine's home to the code,
    which then honors CODEX_HOME and CLAUDE_CONFIG_DIR: never let those reach the real ones."""
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
