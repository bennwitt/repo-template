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


def _record(home: Path, key: str, where: str, *, fresh: bool = False) -> dict[str, Any]:
    """What repo-template wrote to this config file before. `fresh`: the file isn't there (a
    new machine, or a reset), so nothing in the record holds any more. Raises ValueError for
    an unreadable state file."""
    record = read_state(home).get(key)
    if not isinstance(record, dict) or record.get("version") != RECORD_VERSION:
        record = {}
    if record.get("path") != where or fresh:  # another or a new file: nothing in it is ours
        record = {}

    def table(field: str) -> dict[str, Any]:
        value = record.get(field)
        return dict(value) if isinstance(value, dict) else {}

    return {
        "version": RECORD_VERSION,
        "path": where,
        "owned": table("owned"),
        "kept": table("kept"),
        "removed": table("removed"),
    }


def _save(home: Path, key: str, record: dict[str, Any]) -> None:
    state = read_state(home)
    if state.get(key) != record:
        write_state(home, {**state, key: record})


def _duplicates(
    current: Mapping[str, Any], managed: Mapping[str, Server], ours: set[str]
) -> list[tuple[str, str]]:
    """(entry, server) for entries repo-template doesn't own that run one of `managed`, the
    servers this client gets from it, under another name: the same URL, or the same package."""
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
        adoptable: set[str] | None = None,
    ) -> None:
        """`adoptable`: the entries repo-template could rewrite, if not all of them (Codex: only
        a [mcp_servers.<name>] table, not an inline table or dotted keys)."""
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
                if mine is not None or name in removed or name in kept:  # removed: stays so
                    if removed.get(name) != want:
                        result.preserved.append(f"{label}.{name} (removed on this machine; kept)")
                    new_removed[name] = want
                    continue
                self.add[name] = entry
                continue
            got = digest(have)
            can_own = adoptable is None or name in adoptable
            if got == want or (
                isinstance(mine, dict) and mine == {"stored": got, "rendered": want}
            ):
                if can_own:
                    self.owned[name] = (
                        mine if isinstance(mine, dict) else {"stored": got, "rendered": want}
                    )
                result.unchanged.append(f"{label}.{name}")
                continue
            if can_own and isinstance(mine, dict) and mine.get("stored") == got:
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

    def exists(self) -> bool: ...

    def servers(self) -> dict[str, Any] | None: ...

    def add(self, name: str, entry: Mapping[str, Any]) -> Completed: ...

    def remove(self, name: str) -> Completed: ...


def claude_config(home: Path) -> Path:
    """The file Claude Code keeps its user-scope servers in: <config dir>/.config.json when that
    legacy file exists, else ~/.claude.json (or $CLAUDE_CONFIG_DIR/.claude.json)."""
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    legacy = Path(configured or home / ".claude") / ".config.json"
    return legacy if legacy.exists() else Path(configured or home) / ".claude.json"


class ClaudeCli:
    def __init__(self, home: Path, runner: Runner | None = None) -> None:
        self.home = home
        self.path = claude_config(home)
        self.runner = runner or SubprocessRunner(env={"HOME": str(home)}, timeout=120)

    def available(self) -> bool:
        return self.runner.which("claude")

    def exists(self) -> bool:
        return self.path.exists()

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
    stamp: str = "",
) -> None:
    """Keep Claude Code's user-scope servers in step with the global servers for Claude. The
    config file is backed up under ~/.repo-template/backups/<stamp> before the first change."""
    if claude is None:
        result.notes.append(
            "Claude Code's user-scope MCP servers: skipped (not this machine's home)"
        )
        return
    if not claude.available():  # which, not a run: check and update agree
        result.notes.append("Claude Code's user-scope MCP servers: skipped (no `claude` on PATH)")
        return
    label = f"{claude.path} mcpServers"
    current = claude.servers()
    if current is None:
        result.errors.append(f"cannot read {claude.path}; its MCP servers were left alone")
        return
    record = _record(home, CLAUDE_STATE, str(claude.path), fresh=not claude.exists())
    wanted = {name: claude_entry(server, cache) for name, server in sorted(servers.items())}
    plan = _Plan(wanted, current, record, label, result)
    for name, other in _duplicates(current, servers, set(wanted) | set(record["owned"])):
        result.notes.append(
            f"{label}.{name} runs the {other} server repo-template installs; remove it with "
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
    if stamp and claude.path.is_file():
        _backup(claude.path, home / ".repo-template/backups" / stamp / claude.path.name)
    owned = dict(plan.owned)
    for name, entry in plan.add.items():
        if _run(claude.add(name, entry), f"{label}.{name}", result, None):
            _own(claude, name, entry, f"{label}.{name}", result, result.created, owned)
    for name, (entry, old) in plan.replace.items():
        if not _run(claude.remove(name), f"{label}.{name}", result, None):
            owned[name] = record["owned"][name]
            continue
        if _run(claude.add(name, entry), f"{label}.{name}", result, None):
            _own(claude, name, entry, f"{label}.{name}", result, result.updated, owned)
        elif _run(claude.add(name, old), f"{label}.{name} (putting it back)", result, None):
            owned[name] = record["owned"][name]
        # else: gone, and not ours any more, so the next run adds it again
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


def _own(
    claude: ClaudeMcp,
    name: str,
    entry: Mapping[str, Any],
    label: str,
    result: Result,
    into: list[str],
    owned: dict[str, Any],
) -> None:
    """Record what `claude` stored for an entry it just added (it normalizes), next to what was
    rendered, so a later Claude Code that normalizes differently doesn't make the entry look
    changed by hand. An entry not in the file afterwards was written somewhere else."""
    stored = (claude.servers() or {}).get(name)
    if stored is None:
        result.errors.append(f"{label}: `claude mcp add-json` didn't write it to {claude.path}")
        return
    into.append(label)
    owned[name] = {"stored": digest(stored), "rendered": digest(entry)}


# Codex.


def codex_config(home: Path, real_home: bool) -> Path:
    base = os.environ.get("CODEX_HOME") if real_home else None
    return Path(base or home / ".codex") / "config.toml"


def remove_tables(text: str, names: set[str]) -> str:
    """The TOML text without the [mcp_servers.<name>] tables (and their subtables) for these
    names, and without repo-template's marker lines."""
    kept: list[str] = []
    pending: list[str] = []  # comments and blank lines: they belong to whatever follows
    dropping = False
    for line in text.splitlines(keepends=True):
        if line.strip() in {BLOCK_START, BLOCK_END}:
            if line.strip() == BLOCK_END:  # what follows the block isn't ours
                dropping, pending = False, []
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            pending.append(line)
            continue
        header = HEADER.match(line)
        if header:
            dropping = _table(header.group(1)) in names
        if not dropping:
            kept += pending
            kept.append(line)
        pending = []
    return "".join(kept + ([] if dropping else pending))


def _table(header: str) -> str | None:
    """The server a table header names: mcp_servers.<name>, or one of its subtables."""
    parts = [part.strip().strip('"').strip("'") for part in header.split(".")]
    return parts[1] if len(parts) >= 2 and parts[0] == "mcp_servers" else None


def _tables(text: str) -> set[str]:
    """The servers defined by a [mcp_servers.<name>] table, which remove_tables can rewrite."""
    found = set()
    for line in text.splitlines():
        header = HEADER.match(line)
        if not header or line.lstrip().startswith("[["):
            continue
        name = _table(header.group(1))
        if name is not None and len(header.group(1).split(".")) == 2:
            found.add(name)
    return found


def sync_codex_mcp(
    servers: Mapping[str, Server],
    path: Path,
    home: Path,
    result: Result,
    *,
    check: bool,
    stamp: str,
    cache: str,
) -> None:
    """Keep the global servers for Codex in ~/.codex/config.toml (through a symlink, to the
    file it names)."""
    if not path.parent.is_dir():
        result.notes.append(f"Codex MCP servers: skipped ({path.parent} doesn't exist)")
        return
    label = f"{path} mcp_servers"
    target = Path(os.path.realpath(path))
    original = target.read_bytes() if target.exists() else b""
    try:
        text = original.decode()
        data = tomllib.loads(text)
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        result.errors.append(f"cannot read {path}: {exc}; its MCP servers were left alone")
        return
    current = data.get("mcp_servers", {})
    if not isinstance(current, dict):
        result.errors.append(f"{path}: mcp_servers isn't a table; left alone")
        return
    record = _record(home, CODEX_STATE, str(path), fresh=not target.exists())
    wanted = {name: codex_value(server, cache) for name, server in sorted(servers.items())}
    plan = _Plan(wanted, current, record, label, result, adoptable=_tables(text))
    for name, other in _duplicates(current, servers, set(wanted) | set(record["owned"])):
        result.notes.append(
            f"{label}.{name} runs the {other} server repo-template installs; remove it with "
            f"`codex mcp remove {name}`"
        )
    labels = (
        [(result.created, f"{label}.{name}") for name in plan.add]
        + [(result.updated, f"{label}.{name}") for name in plan.replace]
        + [(result.removed, f"{label}.{name}") for name in plan.remove]
    )
    new_record = {**record, "kept": plan.kept, "removed": plan.removed}
    if check:
        for into, line in labels:
            into.append(line)
        return
    if not plan.changes:
        _save(home, CODEX_STATE, {**new_record, "owned": plan.owned})
        return
    writing = {
        **{name: wanted[name] for name in plan.owned},
        **plan.add,
        **{n: e for n, (e, _) in plan.replace.items()},
    }
    rest = remove_tables(text, set(writing) | set(plan.remove))
    block = "\n".join(codex_toml(name, value) for name, value in sorted(writing.items()))
    updated = rest.rstrip("\n") + ("\n" if rest.strip() else "")
    if block:
        updated += ("\n" if rest.strip() else "") + f"{BLOCK_START}\n{block}{BLOCK_END}\n"
    expected = deepcopy(data)
    servers_now = expected.setdefault("mcp_servers", {})
    for name in plan.remove:
        servers_now.pop(name, None)
    servers_now.update(writing)
    if not servers_now and "mcp_servers" not in data:
        del expected["mcp_servers"]
    try:
        parsed = tomllib.loads(updated)
        if not parsed.get("mcp_servers", True):  # an emptied [mcp_servers] counts as none
            del parsed["mcp_servers"]
        if not expected.get("mcp_servers", True):
            del expected["mcp_servers"]
        if digest(parsed) != digest(expected):
            raise ValueError("the edit would change more than repo-template's servers")
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        result.errors.append(f"{path}: couldn't edit it safely ({exc}); left alone")
        return
    if target.exists():
        _backup(target, home / ".repo-template/backups" / stamp / ".codex/config.toml")
    mode = target.stat().st_mode & 0o777 if target.exists() else 0o600
    try:
        _write_private(target, updated, mode=mode, expected=original if target.exists() else None)
    except (ValueError, OSError) as exc:
        result.errors.append(str(exc))
        return
    for into, line in labels:  # reported once it is written
        into.append(line)
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
