from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".agents/hooks/skill_receipt.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("skill_receipt", HOOK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


skill_receipt = _load()


def _repository(root: Path, mode: str | None = "log", **policy: Any) -> Path:
    (root / ".git").mkdir(parents=True)
    if mode is not None:
        (root / ".ai").mkdir()
        (root / ".ai/receipt-policy.json").write_text(json.dumps({"mode": mode, **policy}))
    return root


def _receipts(root: Path) -> list[dict[str, Any]]:
    log = root / ".ai/skill-receipts.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def _model_event(cwd: Path, **extra: Any) -> dict[str, Any]:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Skill",
        "tool_input": {"skill": "tdd", "args": "add login"},
        "session_id": "s1",
        "cwd": str(cwd),
        **extra,
    }


def test_model_skill_use_is_logged(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")

    assert skill_receipt.record(_model_event(root)) is None

    [receipt] = _receipts(root)
    assert receipt["skill"] == "tdd"
    assert receipt["trigger"] == "model"
    assert receipt["args"] == "add login"
    assert receipt["session"] == "s1"


def test_subagent_skill_use_names_the_agent(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")

    skill_receipt.record(_model_event(root, agent_id="a1", agent_type="general-purpose"))

    [receipt] = _receipts(root)
    assert receipt["trigger"] == "subagent"
    assert receipt["agent"] == "general-purpose"


def test_typed_slash_command_is_logged(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    event = {
        "hook_event_name": "UserPromptExpansion",
        "expansion_type": "slash_command",
        "command_name": "grill-with-docs",
        "command_args": "",
        "command_source": "userSettings",
        "cwd": str(root),
    }

    skill_receipt.record(event)

    [receipt] = _receipts(root)
    assert receipt["skill"] == "grill-with-docs"
    assert receipt["trigger"] == "user"
    assert receipt["source"] == "userSettings"
    assert "args" not in receipt


def test_announce_mode_returns_a_notice(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo", mode="announce")

    output = skill_receipt.record(_model_event(root))

    assert json.loads(output) == {"systemMessage": "Skill receipt: tdd (model)"}
    assert len(_receipts(root)) == 1


@pytest.mark.parametrize("mode", [None, "off", "unknown"])
def test_nothing_is_written_unless_the_repository_opts_in(tmp_path: Path, mode: str | None) -> None:
    root = _repository(tmp_path / "repo", mode=mode)

    assert skill_receipt.record(_model_event(root)) is None
    assert _receipts(root) == []


def test_other_events_are_ignored(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    event = _model_event(root, tool_name="Bash", tool_input={"command": "ls"})

    skill_receipt.record(event)

    assert _receipts(root) == []


def test_policy_is_found_from_a_subdirectory_but_not_past_the_git_root(tmp_path: Path) -> None:
    outer = _repository(tmp_path / "outer")
    nested = _repository(outer / "vendor/nested", mode=None)
    subdirectory = outer / "src/pkg"
    subdirectory.mkdir(parents=True)

    skill_receipt.record(_model_event(subdirectory))
    skill_receipt.record(_model_event(nested))

    assert len(_receipts(outer)) == 1


def test_log_path_cannot_escape_the_repository(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo", logPath="../outside.jsonl")

    skill_receipt.record(_model_event(root))

    assert not (tmp_path / "outside.jsonl").exists()


def test_hook_exits_zero_on_bad_input() -> None:
    process = subprocess.run(
        [sys.executable, str(HOOK)], input="not json", text=True, capture_output=True
    )

    assert process.returncode == 0
    assert process.stdout == ""


def test_older_log_path_spelling_is_honored(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo", log_path=".ai/skill-usage.log")

    skill_receipt.record(_model_event(root))

    assert json.loads((root / ".ai/skill-usage.log").read_text())["skill"] == "tdd"
    assert not (root / ".ai/skill-receipts.jsonl").exists()
