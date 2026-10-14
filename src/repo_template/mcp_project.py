"""A repository's pack MCP servers: `.mcp.json` (committed, for Claude Code) and an untracked
`.codex/config.toml` block (for Codex).

`.mcp.json` entries are owned by name and digest, recorded under `mcp_servers` in the
repository's manifest: an entry edited in the repository is kept and reported, one no pack uses
any more is removed only if unedited, and the file is deleted only if repo-template's entries
were all it held. The Codex file is per machine (Codex expands no placeholders, so it holds
this machine's paths); its block's digest is in its opening marker. Claude Code asks before it
starts a project server; Codex reads the file only in a project you trust.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repo_template.mcp import Server, claude_entry, codex_toml, codex_value, digest
from repo_template.model import Result
from repo_template.scaffold import write_file
from repo_template.standards import git_ignores

PROJECT_FILE = ".mcp.json"
CODEX_FILE = ".codex/config.toml"
CLAUDE_CACHE = "${HOME}/.cache/repo-template"  # Claude Code expands it on each machine
CODEX_START = "# >>> repo-template pack MCP servers sha256="
CODEX_END = "# <<< repo-template pack MCP servers"
BLOCK = re.compile(
    rf"^{re.escape(CODEX_START)}(?P<digest>[0-9a-f]{{64}})\n(?P<body>.*?)^{re.escape(CODEX_END)}\n",
    re.M | re.S,
)


@dataclass
class McpPlan:
    """What update would do to a repository's MCP files, and the manifest record after it."""

    record: dict[str, str] = field(default_factory=dict)
    claude: dict[str, Any] | None = None  # the new .mcp.json document; None: leave it
    delete_claude: bool = False
    codex: str | None = None  # the new .codex/config.toml text; None: leave it
    delete_codex: bool = False
    labels: list[tuple[str, str]] = field(default_factory=list)  # (kind, label)


def plan_project_mcp(
    root: Path,
    servers: Mapping[str, Server],
    recorded: Mapping[str, str],
    *,
    owned: set[str],
    removals: bool,
    cache: str,
) -> McpPlan:
    """`servers` are the pack servers the repository's packs use; `removals` is False while a
    listed pack isn't defined, since its servers can't be told apart."""
    plan = McpPlan(record=dict(recorded))
    if PROJECT_FILE not in owned:
        _plan_claude(root, servers, recorded, plan, removals)
    if CODEX_FILE not in owned:
        _plan_codex(root, servers, plan, cache)
    return plan


def _plan_claude(
    root: Path,
    servers: Mapping[str, Server],
    recorded: Mapping[str, str],
    plan: McpPlan,
    removals: bool,
) -> None:
    path = root / PROJECT_FILE
    wanted = {
        name: claude_entry(server, CLAUDE_CACHE)
        for name, server in servers.items()
        if "claude" in server.clients
    }
    document: Any = {}
    if path.exists():
        try:
            document = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            document = None
        if not isinstance(document, dict) or not isinstance(document.get("mcpServers", {}), dict):
            if wanted or recorded:
                plan.labels.append(
                    ("preserved", f"{PROJECT_FILE} (not a JSON object with mcpServers; left alone)")
                )
            return
    current: dict[str, Any] = dict(document.get("mcpServers", {}))
    updated = dict(current)
    record: dict[str, str] = {}
    for name, entry in wanted.items():
        have, mine, want = current.get(name), recorded.get(name), digest(entry)
        label = f"{PROJECT_FILE} mcpServers.{name}"
        if have is None:
            updated[name] = entry
            record[name] = want
            plan.labels.append(("created", label))
        elif digest(have) == want:
            record[name] = want
        elif mine is not None and digest(have) == mine:
            updated[name] = entry
            record[name] = want
            plan.labels.append(("updated", label))
        else:
            plan.labels.append(("preserved", f"{label} (edited in this repository; kept)"))
            if mine is not None:
                record[name] = mine
    for name, mine in recorded.items():
        if name in wanted:
            continue
        have = current.get(name)
        if not removals:
            record[name] = mine
        elif have is not None and digest(have) == mine:
            del updated[name]
            plan.labels.append(("removed", f"{PROJECT_FILE} mcpServers.{name}"))
        elif have is not None:
            plan.labels.append(
                (
                    "note",
                    f"{PROJECT_FILE} mcpServers.{name}: no pack uses it, but it was edited; kept",
                )
            )
    plan.record = record
    if updated == current:
        return
    if not updated and set(document) <= {"mcpServers"}:
        plan.delete_claude = path.exists()
        return
    plan.claude = {**document, "mcpServers": updated}


def _plan_codex(root: Path, servers: Mapping[str, Server], plan: McpPlan, cache: str) -> None:
    path = root / CODEX_FILE
    text = path.read_text() if path.is_file() else ""
    found = BLOCK.search(text)
    outside = BLOCK.sub("", text) if found else text
    try:
        defined = tomllib.loads(outside).get("mcp_servers", {})
    except tomllib.TOMLDecodeError:
        plan.labels.append(("preserved", f"{CODEX_FILE} (not valid TOML; left alone)"))
        return
    wanted = {
        name: codex_value(server, cache)
        for name, server in servers.items()
        if "codex" in server.clients
    }
    for name in sorted(set(wanted) & set(defined)):
        plan.labels.append(
            (
                "note",
                f"{CODEX_FILE} mcp_servers.{name} is defined outside the repo-template "
                f"block; left as it is",
            )
        )
        del wanted[name]
    if found and digest(found.group("body")) != found.group("digest"):
        plan.labels.append(
            ("preserved", f"{CODEX_FILE} (edited inside the repo-template block; kept)")
        )
        return
    body = "\n".join(codex_toml(name, value) for name, value in sorted(wanted.items()))
    block = f"{CODEX_START}{digest(body)}\n{body}{CODEX_END}\n" if body else ""
    if found:
        new = text[: found.start()] + block + text[found.end() :]
    elif block:
        new = text.rstrip("\n") + ("\n\n" if text.strip() else "") + block
    else:
        return
    if new == text:
        return
    if path not in git_ignores(root)([path]):  # it holds this machine's paths: never commit it
        plan.labels.append(
            (
                "preserved",
                f"{CODEX_FILE} (Git doesn't ignore it here; not written, since it "
                f"would hold this machine's paths)",
            )  # fmt: skip
        )
        return
    try:
        tomllib.loads(new)
    except tomllib.TOMLDecodeError as exc:  # never write a file that breaks Codex here
        plan.labels.append(("preserved", f"{CODEX_FILE} (couldn't add the block: {exc})"))
        return
    if not new.strip():
        plan.delete_codex = True
        plan.labels.append(("removed", CODEX_FILE))
        return
    plan.codex = new
    plan.labels.append(
        ("updated" if path.exists() else "created", f"{CODEX_FILE} (pack MCP servers)")
    )


def apply_project_mcp(root: Path, plan: McpPlan, result: Result, *, check: bool) -> None:
    for kind, label in plan.labels:
        {"created": result.created, "updated": result.updated, "removed": result.removed,
         "preserved": result.preserved, "note": result.notes}[kind].append(label)  # fmt: skip
    if check:
        return
    if plan.claude is not None:
        write_file(root, PROJECT_FILE, json.dumps(plan.claude, indent=2, ensure_ascii=False) + "\n")
    elif plan.delete_claude:
        (root / PROJECT_FILE).unlink(missing_ok=True)
    if plan.codex is not None or plan.delete_codex:
        path = root / CODEX_FILE
        if plan.delete_codex:
            path.unlink(missing_ok=True)
            if path.parent.is_dir() and not any(path.parent.iterdir()):
                path.parent.rmdir()
        else:
            write_file(root, CODEX_FILE, plan.codex or "")
        if plan.codex is not None:
            result.notes.append(f"Codex reads {CODEX_FILE} only in a project you trust")


def recorded_mcp(manifest: Mapping[str, Any]) -> dict[str, str]:
    value = manifest.get("mcp_servers", {})
    if not isinstance(value, dict):
        return {}
    return {
        name: sha for name, sha in value.items() if isinstance(name, str) and isinstance(sha, str)
    }
