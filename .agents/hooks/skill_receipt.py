#!/usr/bin/env python3
"""Record a receipt each time a skill is used, in repositories that opt in.

Claude Code runs this hook after every Skill tool call (PostToolUse with matcher "Skill"),
including calls made by subagents, and whenever a typed /command expands (UserPromptExpansion).
A repository opts in with .ai/receipt-policy.json:

    {"mode": "announce", "logPath": ".ai/skill-receipts.jsonl"}

mode is "off", "log" (append one JSON line per use) or "announce" (append, and show a one-line
notice in the session). The hook never blocks or fails a session: any problem exits 0 silently.
It runs under any Python 3.8+, because macOS's system python3 is older than this repository's.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

POLICY = Path(".ai/receipt-policy.json")
DEFAULT_LOG = ".ai/skill-receipts.jsonl"
MODES = ("off", "log", "announce")
MAX_ARGS = 200


def receipt_for(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Describe the skill use in a hook event, or return None if the event isn't one."""
    name = event.get("hook_event_name")
    source = None
    if name in ("PreToolUse", "PostToolUse") and event.get("tool_name") == "Skill":
        tool_input = event.get("tool_input") or {}
        skill, args = tool_input.get("skill"), tool_input.get("args")
        trigger = "subagent" if event.get("agent_id") else "model"
    elif name == "UserPromptExpansion" and event.get("expansion_type") == "slash_command":
        skill, args = event.get("command_name"), event.get("command_args")
        trigger, source = "user", event.get("command_source")
    else:
        return None
    if not isinstance(skill, str) or not skill:
        return None
    receipt = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "skill": skill,
        "trigger": trigger,
        "source": source,
        "agent": event.get("agent_type"),
        "session": event.get("session_id"),
        "args": args[:MAX_ARGS] if isinstance(args, str) and args else None,
    }
    return {key: value for key, value in receipt.items() if value is not None}


def find_policy(start: Path) -> Optional[Path]:
    """Return the nearest receipt policy at or above `start`, stopping at the Git root."""
    for directory in (start, *start.parents):
        if (directory / POLICY).is_file():
            return directory / POLICY
        if (directory / ".git").exists():
            return None
    return None


def record(event: Dict[str, Any]) -> Optional[str]:
    """Append a receipt if the event is a skill use in an opted-in repository.

    Returns the hook's stdout (a systemMessage in announce mode), or None.
    """
    receipt = receipt_for(event)
    if receipt is None:
        return None
    start = event.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    policy_path = find_policy(Path(start).resolve())
    if policy_path is None:
        return None
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or policy.get("mode", "log") not in MODES[1:]:
        return None
    root = policy_path.parent.parent
    log = (root / str(policy.get("logPath") or DEFAULT_LOG)).resolve()
    try:
        log.relative_to(root)
    except ValueError:
        return None
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt) + "\n")
    if policy.get("mode") == "announce":
        notice = f"Skill receipt: {receipt['skill']} ({receipt['trigger']})"
        return json.dumps({"systemMessage": notice})
    return None


def main() -> int:
    try:
        output = record(json.load(sys.stdin))
    except Exception:
        return 0
    if output:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
