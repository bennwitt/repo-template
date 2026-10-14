"""A repository's pack MCP servers: `.mcp.json` (committed, for Claude Code) and an untracked
`.codex/config.toml` block (for Codex).

`.mcp.json` entries are owned by name and digest, recorded under `mcp_servers` in the
repository's manifest. As with global servers, an entry edited in the repository is kept and
reported once, and one deleted from it stays deleted; both are recorded under `mcp_kept`
(delete a name there to have repo-template manage it again). An entry no pack uses any more is
removed only if unedited, and the file is deleted only if repo-template's entries were all it
held. `.mcp.json` is written before the manifest, so an interrupted run records nothing it
didn't write.

The Codex file is per machine (Codex expands no placeholders, so it holds this machine's paths)
and is written only where Git ignores it; its block's digest is in its opening marker. Claude
Code asks before it starts a project server; Codex reads the file only in a project you trust.
"""

from __future__ import annotations

import json
import os
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
DELETED = "deleted"  # in mcp_kept: the entry was deleted from .mcp.json, and stays so
Labels = list[tuple[str, str]]  # (kind, label)


@dataclass
class McpPlan:
    """What update would do to a repository's .mcp.json, and the manifest records after it."""

    record: dict[str, str] = field(default_factory=dict)  # mcp_servers: what repo-template wrote
    kept: dict[str, str] = field(default_factory=dict)  # mcp_kept: edited or deleted entries
    claude: dict[str, Any] | None = None  # the new .mcp.json document; None: leave it
    delete_claude: bool = False
    labels: Labels = field(default_factory=list)

    @property
    def manifest(self) -> dict[str, dict[str, str]]:
        return {"mcp_servers": self.record, "mcp_kept": self.kept}


@dataclass
class CodexPlan:
    text: str | None = None  # the new .codex/config.toml text; None: leave it
    delete: bool = False
    labels: Labels = field(default_factory=list)


def plan_project_mcp(
    root: Path,
    servers: Mapping[str, Server],
    manifest: Mapping[str, Any],
    *,
    owned: set[str],
    removals: bool,
) -> McpPlan:
    """`servers` are the pack servers the repository's packs use; `removals` is False while a
    listed pack isn't defined: its servers, and their args, can't be known, so entries are
    only created, never changed or removed."""
    plan = McpPlan(record=recorded_mcp(manifest), kept=kept_mcp(manifest))
    if PROJECT_FILE not in owned:
        _plan_claude(root, servers, plan, removals)
    return plan


def _plan_claude(root: Path, servers: Mapping[str, Server], plan: McpPlan, removals: bool) -> None:
    path = root / PROJECT_FILE
    recorded, kept = dict(plan.record), dict(plan.kept)
    wanted = {
        name: claude_entry(server, CLAUDE_CACHE)
        for name, server in servers.items()
        if "claude" in server.clients
    }
    document: Any = {}
    if path.exists() or path.is_symlink():
        try:
            document = json.loads(path.read_text()) if not path.is_symlink() else None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
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
    new_kept: dict[str, str] = {}
    for name, entry in wanted.items():
        have, mine, want = current.get(name), recorded.get(name), digest(entry)
        label = f"{PROJECT_FILE} mcpServers.{name}"
        if have is None:
            if mine is not None or name in kept:  # deleted in this repository: stays so
                if kept.get(name) != DELETED:
                    plan.labels.append(("preserved", f"{label} (deleted in this repository; kept)"))
                new_kept[name] = DELETED
                continue
            updated[name] = entry
            record[name] = want
            plan.labels.append(("created", label))
        elif digest(have) == want:
            record[name] = want
        elif mine is not None and digest(have) == mine and removals:
            updated[name] = entry
            record[name] = want
            plan.labels.append(("updated", label))
        elif mine is not None and digest(have) == mine:
            record[name] = mine  # its args may come from a pack that isn't defined here
        else:
            marker = digest(have)
            if kept.get(name) != marker:
                plan.labels.append(("preserved", f"{label} (edited in this repository; kept)"))
            new_kept[name] = marker
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
    if not removals:  # a server of the undefined pack keeps its marker too
        new_kept.update({name: value for name, value in kept.items() if name not in wanted})
    plan.record, plan.kept = record, new_kept
    if updated == current:
        return
    if not updated and set(document) <= {"mcpServers"}:
        plan.delete_claude = path.exists()
        return
    plan.claude = {**document, "mcpServers": updated}


def plan_codex_mcp(
    root: Path,
    servers: Mapping[str, Server],
    *,
    owned: set[str],
    removals: bool,
    cache: str,
    ignored: bool | None = None,
) -> CodexPlan:
    """The repository's .codex/config.toml block. `ignored`: whether Git will ignore the file,
    when update is about to write the .gitignore that decides it (check mode); None asks Git."""
    plan = CodexPlan()
    if CODEX_FILE in owned or not removals:
        return plan  # an undefined pack's servers can't be told apart: the block stays
    folder, path = root / ".codex", root / CODEX_FILE
    real_root = root.resolve()
    if folder.is_symlink() or folder.exists():
        real = folder.resolve()
        if not folder.is_dir() or (real != real_root and real_root not in real.parents):
            if servers:
                plan.labels.append(
                    ("preserved", ".codex (not a folder in this repository; left alone)")
                )
            return plan
    if path.is_symlink() or (path.exists() and not path.is_file()):
        if servers:
            plan.labels.append(("preserved", f"{CODEX_FILE} (not a plain file; left alone)"))
        return plan
    try:
        text = path.read_text() if path.is_file() else ""
    except (OSError, UnicodeDecodeError):
        plan.labels.append(("preserved", f"{CODEX_FILE} (can't be read; left alone)"))
        return plan
    found = BLOCK.search(text)
    outside = BLOCK.sub("", text) if found else text
    try:
        defined = tomllib.loads(outside).get("mcp_servers", {})
    except tomllib.TOMLDecodeError:
        plan.labels.append(("preserved", f"{CODEX_FILE} (not valid TOML; left alone)"))
        return plan
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
        return plan
    body = "\n".join(codex_toml(name, value) for name, value in sorted(wanted.items()))
    block = f"{CODEX_START}{digest(body)}\n{body}{CODEX_END}\n" if body else ""
    if found:
        new = text[: found.start()] + block + text[found.end() :]
    elif block:
        new = text.rstrip("\n") + ("\n\n" if text.strip() else "") + block
    else:
        return plan
    if new == text:
        return plan
    if not (ignored if ignored is not None else path in git_ignores(root)([path])):
        plan.labels.append(  # it holds this machine's paths: never commit it
            (
                "preserved",
                f"{CODEX_FILE} (Git doesn't ignore it here; not written, since it "
                f"would hold this machine's paths)",
            )  # fmt: skip
        )
        return plan
    try:
        tomllib.loads(new)
    except tomllib.TOMLDecodeError as exc:  # never write a file that breaks Codex here
        plan.labels.append(("preserved", f"{CODEX_FILE} (couldn't add the block: {exc})"))
        return plan
    if not new.strip():
        plan.delete = True
        plan.labels.append(("removed", CODEX_FILE))
        return plan
    plan.text = new
    plan.labels.append(
        ("updated" if path.exists() else "created", f"{CODEX_FILE} (pack MCP servers)")
    )
    return plan


def _report(labels: Labels, result: Result) -> None:
    for kind, label in labels:
        {"created": result.created, "updated": result.updated, "removed": result.removed,
         "preserved": result.preserved, "note": result.notes}[kind].append(label)  # fmt: skip


def apply_project_mcp(root: Path, plan: McpPlan, result: Result, *, check: bool) -> None:
    """Write .mcp.json; the manifest that records it is written after."""
    _report(plan.labels, result)
    if check:
        return
    if plan.claude is not None:
        write_file(root, PROJECT_FILE, json.dumps(plan.claude, indent=2, ensure_ascii=False) + "\n")
    elif plan.delete_claude:
        (root / PROJECT_FILE).unlink(missing_ok=True)


def apply_codex_mcp(root: Path, plan: CodexPlan, result: Result, *, check: bool) -> None:
    _report(plan.labels, result)
    if check or (plan.text is None and not plan.delete):
        return
    path = root / CODEX_FILE
    if plan.delete:
        path.unlink(missing_ok=True)
        if path.parent.is_dir() and not any(path.parent.iterdir()):
            path.parent.rmdir()
        return
    path.parent.mkdir(exist_ok=True)
    temporary = path.with_name(f".{path.name}.repo-template-tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(plan.text or "")
    os.replace(temporary, path)
    result.notes.append(f"Codex reads {CODEX_FILE} only in a project you trust")


def _names(manifest: Mapping[str, Any], key: str) -> dict[str, str]:
    value = manifest.get(key, {})
    if not isinstance(value, dict):
        return {}
    return {
        name: sha for name, sha in value.items() if isinstance(name, str) and isinstance(sha, str)
    }


def recorded_mcp(manifest: Mapping[str, Any]) -> dict[str, str]:
    return _names(manifest, "mcp_servers")


def kept_mcp(manifest: Mapping[str, Any]) -> dict[str, str]:
    return _names(manifest, "mcp_kept")
