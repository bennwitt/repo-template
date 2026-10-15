"""globals --upgrade for MCP servers: move a server's pin to its newest final release that is at
least a week old (pins.COOLDOWN), in .agents/mcp-servers.json.

The pin, its publishedAt and the version in the server's args move together, and a pinException
goes once the new release no longer needs it. A catalog file that names the old version (a skill
derived from the same package, say) is reported, not edited.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from repo_template.catalog import PACKS_DIR, SKILLS_DIR
from repo_template.mcp import MCP_SERVERS_NAME, load_mcp_servers
from repo_template.pins import COOLDOWN, FINAL, Registry, _key, _stamp

SERVER_PREFIX = "mcp:"  # `globals --upgrade mcp:<name>`, when a skill has the same name


@dataclass
class Repin:
    """One server's move to a newer release."""

    name: str
    package: str
    old: str
    new: str
    published: str
    entry: dict[str, Any]  # the server's catalog entry afterwards
    diff: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)  # catalog files naming the old version


def _catalog(root: Path) -> dict[str, Any]:
    data = json.loads((root / ".agents" / MCP_SERVERS_NAME).read_text())
    if not isinstance(data, dict) or not isinstance(data.get("servers"), dict):
        raise ValueError(f"{MCP_SERVERS_NAME} has no 'servers' object")
    return data


def server_names(root: Path) -> set[str]:
    path = root / ".agents" / MCP_SERVERS_NAME
    return set(_catalog(root)["servers"]) if path.is_file() else set()


def _spelling(registry: str, package: str, version: str) -> str:
    """How an arg names the pinned release: npx's `pkg@1.2.3`, uvx's `pkg==1.2.3`."""
    return f"{package}@{version}" if registry == "npm" else f"{package}=={version}"


def _mentions(root: Path, needle: str) -> list[str]:
    found = []
    for folder in (root / SKILLS_DIR, root / PACKS_DIR):
        for path in sorted(folder.rglob("*")) if folder.is_dir() else []:
            if path.is_file() and not path.is_symlink():
                try:
                    if needle in path.read_text():
                        found.append(path.relative_to(root).as_posix())
                except (OSError, UnicodeDecodeError):
                    continue
    return found


def plan_repin(root: Path, name: str, registry: Registry, now: datetime) -> Repin | None:
    """The move for `name`, or None when its pin is already the newest release past the
    cooldown. Raises ValueError when the server can't be re-pinned, NetworkError (and NotFound)
    from `registry`."""
    servers = _catalog(root)["servers"]
    entry = servers.get(name)
    if not isinstance(entry, dict):
        raise ValueError(f"{name}: not a server in {MCP_SERVERS_NAME}")
    pin = entry.get("pin")
    if not isinstance(pin, dict):
        raise ValueError(f"{name}: has no pin (a URL server runs whatever its host serves)")
    kind, package, old = pin.get("registry"), pin.get("package"), pin.get("version")
    if not (isinstance(kind, str) and isinstance(package, str) and isinstance(old, str)):
        raise ValueError(f"{name}: its pin needs a registry, a package and a version")
    releases = registry.releases(kind, package)
    ripe = {
        version: when
        for version, when in releases.items()
        if FINAL.fullmatch(version) and now - when >= COOLDOWN
    }
    if FINAL.fullmatch(old):
        ripe = {version: when for version, when in ripe.items() if _key(version) > _key(old)}
    if not ripe:
        return None
    new = max(ripe, key=_key)
    before, after = _spelling(kind, package, old), _spelling(kind, package, new)
    args = entry.get("args", [])
    holding = [i for i, arg in enumerate(args) if isinstance(arg, str) and before in arg]
    if len(holding) != 1:
        raise ValueError(
            f"{name}: its args name {before!r} {len(holding)} times, not once; re-pin it by hand"
        )
    updated = json.loads(json.dumps(entry))
    updated["args"][holding[0]] = args[holding[0]].replace(before, after)
    updated["pin"]["version"] = new
    updated["pin"]["publishedAt"] = _stamp(ripe[new])
    updated["pin"].pop("pinException", None)  # past the cooldown: no exception needed
    diff = list(
        difflib.unified_diff(
            json.dumps(entry, indent=2).splitlines(),
            json.dumps(updated, indent=2).splitlines(),
            f"{name} (pinned {old})",
            f"{name} ({new})",
            lineterm="",
        )
    )
    return Repin(name, package, old, new, _stamp(ripe[new]), updated, diff, _mentions(root, before))


def apply_repin(root: Path, repin: Repin) -> None:
    """Write the move into the catalog, keeping its layout; a catalog the loader refuses
    afterwards is put back, and the reason raised as ValueError."""
    path = root / ".agents" / MCP_SERVERS_NAME
    original = path.read_text()
    data = _catalog(root)
    data["servers"][repin.name] = repin.entry
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    try:
        load_mcp_servers(root / ".agents")
    except ValueError:
        path.write_text(original)
        raise
