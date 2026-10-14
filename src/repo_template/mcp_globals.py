"""Global MCP servers: Claude Code's user scope (~/.claude.json) and ~/.codex/config.toml.

Each server repo-template installs is owned by name and by a digest of the entry as written,
recorded in ~/.repo-template/globals-state.json, never by markers: Codex rewrites comments and
regroups tables whenever it edits the file. As with portable settings, an entry changed on the
machine is kept and reported once, and one removed on the machine stays removed. Claude Code's
file is written only through `claude mcp add-json` and `claude mcp remove`; `--check` reads it
and runs nothing (every `claude` run writes the file).
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

from repo_template.mcp import Server, claude_entry, codex_toml, codex_value, digest
from repo_template.model import Result
from repo_template.runner import Completed, Runner, SubprocessRunner
from repo_template.settings import _backup, _write_private, read_state, write_state

CLAUDE_STATE = "claude_mcp"
CODEX_STATE = "codex_mcp"
RECORD_VERSION = 1
BLOCK_START = "# >>> repo-template MCP servers (each owned by name; see ~/.repo-template)"
BLOCK_END = "# <<< repo-template MCP servers"
HEADER = re.compile(r"^\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(?:#.*)?$")


def _record(home: Path, key: str, where: str) -> dict[str, Any]:
    record = read_state(home).get(key)
    if not isinstance(record, dict) or record.get("version") != RECORD_VERSION:
        record = {}
    if record.get("path") != where:  # another config file: nothing in it is ours yet
        record = {}
    return {
        "version": RECORD_VERSION,
        "path": where,
        "owned": dict(record.get("owned") or {}),
        "kept": dict(record.get("kept") or {}),
        "removed": dict(record.get("removed") or {}),
    }


def _save(home: Path, key: str, record: dict[str, Any]) -> None:
    state = read_state(home)
    if state.get(key) != record:
        write_state(home, {**state, key: record})


def _duplicates(
    current: Mapping[str, Any], managed: Mapping[str, Server], ours: set[str]
) -> list[tuple[str, str]]:
    """(entry, managed server) for entries repo-template doesn't own that run a server it
    manages under another name: the same URL, or the same npm/PyPI package."""
    found = []
    for name, entry in sorted(current.items()):
        if name in ours or not isinstance(entry, dict):
            continue
        text = json.dumps(entry)
        for server in managed.values():
            url = str(entry.get("url", "")).rstrip("/")
            same_url = server.url is not None and url == server.url.rstrip("/")
            same_package = server.pin is not None and f'"{server.pin.package}@' in text
            if same_url or same_package:
                found.append((name, server.name))
    return found


class _Plan:
    """What to do with each server, from the entries as they are and the record."""

    def __init__(
        self,
        wanted: Mapping[str, dict[str, Any]],
        current: Mapping[str, Any],
        record: dict[str, Any],
        label: str,
        result: Result,
    ) -> None:
        self.add: dict[str, dict[str, Any]] = {}
        self.replace: dict[str, tuple[dict[str, Any], Any]] = {}
        self.remove: dict[str, Any] = {}
        self.owned: dict[str, Any] = {}
        owned, kept, removed = record["owned"], record["kept"], record["removed"]
        new_kept: dict[str, Any] = {}
        new_removed: dict[str, Any] = {}
        for name, entry in wanted.items():
            want = digest(entry)
            have = current.get(name)
            mine = owned.get(name)
            if have is None:
                if mine is not None or name in removed:  # removed on this machine: stays so
                    if removed.get(name) != want:
                        result.preserved.append(f"{label}.{name} (removed on this machine; kept)")
                    new_removed[name] = want
                    continue
                self.add[name] = entry
                continue
            got = digest(have)
            if got == want or (
                isinstance(mine, dict) and mine == {"stored": got, "rendered": want}
            ):
                self.owned[name] = (
                    mine if isinstance(mine, dict) else {"stored": got, "rendered": want}
                )
                result.unchanged.append(f"{label}.{name}")
                continue
            if isinstance(mine, dict) and mine.get("stored") == got:
                self.replace[name] = (entry, have)
                continue
            marker = [got, want]
            if kept.get(name) != marker:
                result.preserved.append(f"{label}.{name} (configured by hand; kept)")
            new_kept[name] = marker
        for name, mine in owned.items():
            if name in wanted or name not in current:
                continue
            if isinstance(mine, dict) and digest(current[name]) == mine.get("stored"):
                self.remove[name] = current[name]  # dropped from the catalog
        self.kept, self.removed = new_kept, new_removed

    @property
    def changes(self) -> bool:
        return bool(self.add or self.replace or self.remove)


# Claude Code.


class ClaudeMcp(Protocol):
    """Claude Code's user-scope MCP servers. Production runs the `claude` CLI; tests use an
    in-memory fake."""

    path: Path

    def available(self) -> bool: ...

    def servers(self) -> dict[str, Any] | None: ...

    def add(self, name: str, entry: Mapping[str, Any]) -> Completed: ...

    def remove(self, name: str) -> Completed: ...


class ClaudeCli:
    def __init__(self, home: Path, runner: Runner | None = None) -> None:
        self.home = home
        self.path = Path(os.environ.get("CLAUDE_CONFIG_DIR") or home) / ".claude.json"
        self.runner = runner or SubprocessRunner(env={"HOME": str(home)}, timeout=120)

    def available(self) -> bool:
        return self.runner.which("claude")

    def servers(self) -> dict[str, Any] | None:
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        servers = data.get("mcpServers", {}) if isinstance(data, dict) else None
        return servers if isinstance(servers, dict) else None

    def add(self, name: str, entry: Mapping[str, Any]) -> Completed:
        payload = json.dumps(entry, separators=(",", ":"))
        # cwd=home, so no project .mcp.json or local-scope entry can get in the way
        return self.runner.run(
            ["claude", "mcp", "add-json", "--scope", "user", name, payload], self.home
        )

    def remove(self, name: str) -> Completed:
        return self.runner.run(["claude", "mcp", "remove", "--scope", "user", name], self.home)


def sync_claude_mcp(
    servers: Mapping[str, Server],
    claude: ClaudeMcp | None,
    home: Path,
    result: Result,
    *,
    check: bool,
    cache: str,
    managed: Mapping[str, Server],
    stamp: str = "",
) -> None:
    """Keep Claude Code's user-scope servers in step with the global servers for Claude. The
    config file is backed up under ~/.repo-template/backups/<stamp> before the first change."""
    if claude is None:
        result.notes.append(
            "Claude Code's user-scope MCP servers: skipped (not this machine's home)"
        )
        return
    label = f"{claude.path} mcpServers"
    current = claude.servers()
    if current is None:
        result.errors.append(f"cannot read {claude.path}; its MCP servers were left alone")
        return
    record = _record(home, CLAUDE_STATE, str(claude.path))
    wanted = {name: claude_entry(server, cache) for name, server in sorted(servers.items())}
    plan = _Plan(wanted, current, record, label, result)
    for name, other in _duplicates(current, managed, set(wanted) | set(record["owned"])):
        result.notes.append(
            f"{label}.{name} runs the {other} server repo-template manages; remove it with "
            f"`claude mcp remove {name} --scope user`"
        )
    if check or not plan.changes:
        result.created += [f"{label}.{name}" for name in plan.add]
        result.updated += [f"{label}.{name}" for name in plan.replace]
        result.removed += [f"{label}.{name}" for name in plan.remove]
        if not check:
            _save(
                home,
                CLAUDE_STATE,
                {**record, "owned": plan.owned, "kept": plan.kept, "removed": plan.removed},
            )
        return
    if not claude.available():
        result.notes.append("Claude Code's user-scope MCP servers: skipped (no `claude` on PATH)")
        return
    if stamp and claude.path.is_file():
        _backup(claude.path, home / ".repo-template/backups" / stamp / claude.path.name)
    owned = dict(plan.owned)
    for name, entry in plan.add.items():
        if _run(claude.add(name, entry), f"{label}.{name}", result, result.created):
            owned[name] = _stored(claude, name, entry)
    for name, (entry, old) in plan.replace.items():
        if not _run(claude.remove(name), f"{label}.{name}", result, None):
            owned[name] = record["owned"][name]
            continue
        if _run(claude.add(name, entry), f"{label}.{name}", result, result.updated):
            owned[name] = _stored(claude, name, entry)
        else:
            claude.add(name, old)  # put back what was there
            owned[name] = record["owned"][name]
    for name in plan.remove:
        if _run(claude.remove(name), f"{label}.{name}", result, result.removed):
            continue
        owned[name] = record["owned"][name]
    _save(
        home, CLAUDE_STATE, {**record, "owned": owned, "kept": plan.kept, "removed": plan.removed}
    )


def _run(done: Completed, label: str, result: Result, into: list[str] | None) -> bool:
    if done.code:
        result.errors.append(
            f"{label}: {(done.err or done.out).strip()[:300] or f'exit {done.code}'}"
        )
        return False
    if into is not None:
        into.append(label)
    return True


def _stored(claude: ClaudeMcp, name: str, entry: Mapping[str, Any]) -> dict[str, str]:
    """What `claude` stored for an entry (it normalizes), next to what was rendered, so a later
    Claude Code that normalizes differently doesn't make the entry look changed by hand."""
    stored = (claude.servers() or {}).get(name, entry)
    return {"stored": digest(stored), "rendered": digest(entry)}


# Codex.


def codex_config(home: Path, real_home: bool) -> Path:
    base = os.environ.get("CODEX_HOME") if real_home else None
    return Path(base or home / ".codex") / "config.toml"


def remove_tables(text: str, names: set[str]) -> str:
    """The TOML text without the [mcp_servers.<name>] tables (and their subtables) for these
    names, and without repo-template's marker lines."""
    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    dropping = False
    for line in lines:
        header = HEADER.match(line)
        if header:
            parts = [part.strip().strip('"') for part in header.group(1).split(".")]
            dropping = len(parts) >= 2 and parts[0] == "mcp_servers" and parts[1] in names
        if line.strip() in {BLOCK_START, BLOCK_END}:
            continue
        if not dropping:
            kept.append(line)
    return "".join(kept)


def sync_codex_mcp(
    servers: Mapping[str, Server],
    path: Path,
    home: Path,
    result: Result,
    *,
    check: bool,
    stamp: str,
    cache: str,
    managed: Mapping[str, Server],
) -> None:
    """Keep the global servers for Codex in ~/.codex/config.toml."""
    if not path.parent.is_dir():
        result.notes.append(f"Codex MCP servers: skipped ({path.parent} doesn't exist)")
        return
    label = f"{path} mcp_servers"
    original = path.read_bytes() if path.exists() else b""
    try:
        data = tomllib.loads(original.decode())
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        result.errors.append(f"cannot read {path}: {exc}; its MCP servers were left alone")
        return
    current = data.get("mcp_servers", {})
    if not isinstance(current, dict):
        result.errors.append(f"{path}: mcp_servers isn't a table; left alone")
        return
    record = _record(home, CODEX_STATE, str(path))
    wanted = {name: codex_value(server, cache) for name, server in sorted(servers.items())}
    plan = _Plan(wanted, current, record, label, result)
    for name, other in _duplicates(current, managed, set(wanted) | set(record["owned"])):
        result.notes.append(
            f"{label}.{name} runs the {other} server repo-template manages; remove it with "
            f"`codex mcp remove {name}`"
        )
    result.created += [f"{label}.{name}" for name in plan.add]
    result.updated += [f"{label}.{name}" for name in plan.replace]
    result.removed += [f"{label}.{name}" for name in plan.remove]
    new_record = {**record, "kept": plan.kept, "removed": plan.removed}
    if check:
        return
    if not plan.changes:
        _save(home, CODEX_STATE, {**new_record, "owned": plan.owned})
        return
    writing = {
        **{name: wanted[name] for name in plan.owned},
        **plan.add,
        **{n: e for n, (e, _) in plan.replace.items()},
    }
    text = remove_tables(original.decode(), set(writing) | set(plan.remove))
    block = "\n".join(codex_toml(name, value) for name, value in sorted(writing.items()))
    updated = (
        text.rstrip("\n")
        + ("\n\n" if text.strip() else "")
        + f"{BLOCK_START}\n{block}{BLOCK_END}\n"
    )
    expected = deepcopy(data)
    servers_now = expected.setdefault("mcp_servers", {})
    for name in plan.remove:
        servers_now.pop(name, None)
    servers_now.update(writing)
    try:
        if digest(tomllib.loads(updated)) != digest(expected):
            raise ValueError("the edit would change more than repo-template's servers")
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        result.errors.append(f"{path}: couldn't edit it safely ({exc}); left alone")
        return
    backup = home / ".repo-template/backups" / stamp / ".codex/config.toml"
    if path.exists():
        _backup(path, backup)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    try:
        _write_private(path, updated, mode=mode, expected=original if path.exists() else None)
    except (ValueError, OSError) as exc:
        result.errors.append(str(exc))
        return
    _save(
        home,
        CODEX_STATE,
        {
            **new_record,
            "owned": {
                name: {"stored": digest(value), "rendered": digest(value)}
                for name, value in writing.items()
            },
        },
    )
