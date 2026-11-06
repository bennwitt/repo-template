"""Explicit native-plugin selection and offline, evidence-backed duplicate suppression."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from repo_template.maintenance import atomic_json, fingerprint, read_json
from repo_template.model import Result

SELECTOR = re.compile(r"(codex|claude):([a-z0-9][a-z0-9_-]*@[a-z0-9][a-z0-9_-]*)")
Run = Callable[[Sequence[str]], Any]


def state_path(home: Path) -> Path:
    return home / ".repo-template/capabilities.json"


def native_state(home: Path, client: str) -> str:
    paths = (
        [home / ".codex/config.toml", home / ".codex/plugins/installed_plugins.json"]
        if client == "codex"
        else [home / ".claude/settings.json", home / ".claude/plugins/installed_plugins.json"]
    )
    configuration: dict[str, Any] = {}
    for path in paths:
        if not path.is_file():
            configuration[str(path)] = None
        elif path.suffix == ".toml":
            try:
                data = tomllib.loads(path.read_text())
            except (OSError, ValueError):
                return ""
            configuration[str(path)] = {
                k: v for k, v in data.items() if "plugin" in k or "marketplace" in k
            }
        elif path.name == "settings.json":
            try:
                data = json.loads(path.read_text())
                if not isinstance(data, dict):
                    return ""
            except (OSError, ValueError):
                return ""
            configuration[str(path)] = {
                k: v for k, v in data.items() if "plugin" in k.lower() or "marketplace" in k.lower()
            }
        else:
            try:
                configuration[str(path)] = json.loads(path.read_text())
            except (OSError, ValueError):
                return ""
    return fingerprint(configuration)


def tree_digest(path: Path) -> str | None:
    try:
        return _tree_digest(path)
    except OSError:
        return None


def _tree_digest(path: Path) -> str | None:
    if not path.is_dir() or path.is_symlink():
        return None
    digest = hashlib.sha256()
    total = 0
    for index, file in enumerate(sorted(path.rglob("*"))):
        if index > 10000 or file.is_symlink():
            return None
        if file.is_file():
            total += file.stat().st_size
            if total > 50 * 1024 * 1024:
                return None
            digest.update(file.relative_to(path).as_posix().encode() + b"\0")
            digest.update(str(file.stat().st_mode & 0o111).encode() + b"\0")
            digest.update(hashlib.sha256(file.read_bytes()).digest())
    return digest.hexdigest()


def providers(agents: Path) -> dict[str, Any]:
    result = read_json(agents / "skill-sources.json").get("plugins", {})
    if not isinstance(result, dict):
        raise ValueError("skill-sources.json plugins must be an object")
    return result


def _marketplace(document: Any, plugin: str, source: str) -> bool:
    rows = document.get("marketplaces", []) if isinstance(document, dict) else document
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, dict) or row.get("name") != plugin.split("@")[1]:
            continue
        origin = row.get("marketplaceSource", row.get("source", {}))
        if isinstance(origin, dict):
            origin = origin.get("repo", origin.get("source", origin.get("url", "")))
        if isinstance(origin, str):
            origin = origin.split("#")[0].split("@")[0]
            origin = origin.removeprefix("https://github.com/").removesuffix(".git")
            if origin == source:
                return True
    return False


def _assets(path: Path, plugin: str, provider: dict[str, Any], agents: Path) -> dict[str, Any]:
    manifest = next(
        (
            read_json(path / p)
            for p in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "plugin.json")
            if (path / p).is_file()
        ),
        {},
    )
    if manifest.get("name") != plugin.split("@")[0]:
        raise ValueError(f"{plugin}: native manifest identity is unverified; fallback retained")
    skills = {p.parent.name for p in path.rglob("SKILL.md") if p.is_file()}
    mcp = read_json(path / ".mcp.json").get("mcpServers", {})
    servers = read_json(agents / "mcp-servers.json").get("servers", {})
    confirmed_mcp = []
    for name in provider.get("mcp", []):
        wanted = servers.get(name, {})
        if name in mcp or any(
            wanted.get("url") and s.get("url") == wanted["url"]
            for s in mcp.values()
            if isinstance(s, dict)
        ):
            confirmed_mcp.append(name)
    return {"skills": sorted(skills & set(provider.get("skills", []))), "mcp": confirmed_mcp}


def _reviewed_candidate(document: Any, plugin: str, provider: dict[str, Any], invoke: Run) -> None:
    """Before native installation, require the reviewed immutable local plugin subtree."""
    rows = document.get("marketplaces", []) if isinstance(document, dict) else document
    if not _marketplace(document, plugin, provider["source"]):
        raise ValueError("marketplace origin differs from reviewed provider")
    for row in rows:
        if row.get("name") != plugin.split("@")[1]:
            continue
        location = row.get("root", row.get("installLocation"))
        if not isinstance(location, str):
            break
        root = Path(location).resolve()
        revision = invoke(["git", "-C", str(root), "rev-parse", "HEAD"])
        if not isinstance(revision, str) or revision.strip() != provider["reviewedRevision"]:
            break
        manifest = read_json(root / ".claude-plugin/marketplace.json")
        for entry in manifest.get("plugins", []):
            source = entry.get("source")
            if entry.get("name") != plugin.split("@")[0] or not isinstance(source, str):
                continue
            candidate = (root / source).resolve()
            if root in candidate.parents and tree_digest(candidate) == provider["reviewedDigest"]:
                return
    raise ValueError(
        "plugin subtree is not the reviewed revision; "
        "external or floating components require review"
    )


def _installed(document: Any, plugin: str, home: Path, client: str) -> dict[str, Any] | None:
    rows = document.get("installed", []) if isinstance(document, dict) else document
    if not isinstance(rows, list):
        raise ValueError(f"{client} returned an unrecognized plugin listing")
    for row in rows:
        if not isinstance(row, dict) or (row.get("pluginId") or row.get("id")) != plugin:
            continue
        if row.get("enabled") is not True or row.get("installed") is False or row.get("notes"):
            continue
        if row.get("scope", "user") != "user":
            continue
        version = row.get("version")
        if not isinstance(version, str) or not re.fullmatch(r"[\w.+-]+", version):
            continue
        name, market = plugin.split("@")
        path = Path(
            row.get("installPath") or home / f".{client}/plugins/cache" / market / name / version
        )
        if home.resolve() not in path.resolve().parents:
            continue
        digest = tree_digest(path)
        configuration = native_state(home, client)
        if digest and configuration:
            return {
                "version": version,
                "path": str(path),
                "digest": digest,
                "native_state": configuration,
            }
    return None


def _present(document: Any, plugin: str) -> bool:
    rows = document.get("installed", []) if isinstance(document, dict) else document
    return any(
        isinstance(row, dict)
        and (row.get("pluginId") or row.get("id")) == plugin
        and row.get("installed") is not False
        for row in rows
    )


def reconcile(
    agents: Path,
    home: Path,
    selections: Sequence[str],
    removals: Sequence[str],
    *,
    check: bool,
    allow_write: Sequence[str] = (),
    revoke_write: Sequence[str] = (),
    run: Run | None = None,
) -> Result:
    result = Result(agents.parent)
    catalog = providers(agents)
    if set(selections) & set(removals) or set(allow_write) & set(revoke_write):
        raise ValueError("cannot select and remove, or activate and revoke, the same capability")
    for selector in [
        *selections,
        *removals,
        *(s for s in [*allow_write, *revoke_write] if ":" in s),
    ]:
        match = SELECTOR.fullmatch(selector)
        if (
            not match
            or match[2] not in catalog
            or match[1] not in catalog[match[2]].get("clients", [])
        ):
            raise ValueError(f"{selector}: no supported CLIENT:PLUGIN@MARKETPLACE provider")
    state = read_json(state_path(home))
    installed = state.setdefault("plugins", {})
    if not isinstance(installed, dict) or not isinstance(state.get("write_mcp", []), list):
        raise ValueError("invalid machine capability state; restore its last valid copy")
    previous_grants = set(state.get("write_mcp", []))
    grants = set(state.get("write_mcp", []))
    grants.update(allow_write)
    grants.difference_update(revoke_write)
    state["write_mcp"] = sorted(grants)
    removals = list(removals)
    for selector in revoke_write:
        if selector in installed and selector not in removals:
            removals.append(selector)

    def invoke(argv: Sequence[str]) -> Any:
        if run:
            return run(argv)
        done = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "HOME": str(home)},
            check=False,
        )
        if done.returncode:
            raise ValueError(f"{argv[0]} plugin command failed (exit {done.returncode})")
        return json.loads(done.stdout) if "--json" in argv else done.stdout

    for selector in [*selections, *removals]:
        match = SELECTOR.fullmatch(selector)
        if not match:
            raise ValueError("plugin selections use CLIENT:PLUGIN@MARKETPLACE")
        client, plugin = match.groups()
        provider = catalog.get(plugin)
        if not isinstance(provider, dict) or client not in provider.get("clients", []):
            raise ValueError(f"{selector}: no supported provider in the catalog")
        removing = selector in removals
        if provider.get("writeCapable") and not removing and selector not in grants:
            raise ValueError(f"{selector}: requires explicit --allow-write-mcp {selector}")
        if check:
            result.updated.append(selector)
            result.notes.append(
                f"{selector}: {'remove' if removing else 'install'} native plugin; "
                f"source {provider['source']}; {provider.get('review', 'review required')}"
            )
            continue
        fresh_install = False
        try:
            if removing:
                if selector not in installed:
                    result.preserved.append(f"{selector}: not installed by repo-template")
                    continue
                evidence = installed[selector]
                if tree_digest(Path(evidence.get("path", ""))) != evidence.get("digest"):
                    result.preserved.append(
                        f"{selector}: customized plugin retained; remove in the client after review"
                    )
                    if selector in revoke_write:
                        grants.add(selector)
                        result.errors.append(
                            f"{selector}: write access was NOT revoked; "
                            "disable the customized plugin in its client first"
                        )
                    continue
                invoke([client, "plugin", "remove" if client == "codex" else "uninstall", plugin])
                installed.pop(selector, None)
                result.removed.append(selector)
            else:
                markets = invoke([client, "plugin", "marketplace", "list", "--json"])
                verified_market = _marketplace(markets, plugin, provider["source"])
                listing = invoke([client, "plugin", "list", "--json"])
                current = _installed(listing, plugin, home, client)
                if current is None:
                    name, marketplace = plugin.split("@")
                    cached = home / f".{client}/plugins/cache" / marketplace / name
                    if _present(listing, plugin) or cached.exists():
                        raise ValueError(
                            f"{selector}: existing plugin is not confirmed usable; "
                            "review it in the client before replacing it"
                        )
                    revision, digest = (
                        provider.get("reviewedRevision"),
                        provider.get("reviewedDigest"),
                    )
                    if (
                        not isinstance(revision, str)
                        or not re.fullmatch(r"[a-f0-9]{40}", revision)
                        or not isinstance(digest, str)
                        or not re.fullmatch(r"[a-f0-9]{64}", digest)
                    ):
                        raise ValueError(
                            f"{selector}: native installation requires reviewedRevision "
                            "and reviewedDigest in the provider record; "
                            "preview remains review-required"
                        )
                    source = provider["source"]
                    add = (
                        [client, "plugin", "marketplace", "add", source, "--ref", revision]
                        if client == "codex"
                        else [
                            client,
                            "plugin",
                            "marketplace",
                            "add",
                            f"https://github.com/{source}.git#{revision}",
                        ]
                    )
                    invoke(add)
                    _reviewed_candidate(
                        invoke([client, "plugin", "marketplace", "list", "--json"]),
                        plugin,
                        provider,
                        invoke,
                    )
                    fresh_install = True
                    invoke([client, "plugin", "add" if client == "codex" else "install", plugin])
                    current = _installed(
                        invoke([client, "plugin", "list", "--json"]), plugin, home, client
                    )
                    verified_market = _marketplace(
                        invoke([client, "plugin", "marketplace", "list", "--json"]),
                        plugin,
                        provider["source"],
                    )
                    if current and current["digest"] != digest:
                        raise ValueError(
                            f"{selector}: installed content differs from reviewed candidate; "
                            "fallback retained"
                        )
                if current is None:
                    raise ValueError(
                        f"{selector}: installation is not confirmed usable; fallback retained"
                    )
                if not verified_market:
                    raise ValueError(
                        f"{selector}: marketplace origin is unverified; fallback retained"
                    )
                assets = _assets(Path(current["path"]), plugin, provider, agents)
                installed[selector] = {**current, **assets, "provider": fingerprint(provider)}
                missing = set(provider.get("skills", [])) - set(assets["skills"])
                missing.update(set(provider.get("mcp", [])) - set(assets["mcp"]))
                if missing:
                    result.notes.append(
                        f"{selector}: unconfirmed assets retain fallback: "
                        + ", ".join(sorted(missing))
                    )
                result.updated.append(selector)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            result.errors.append(str(exc))
            if removing and selector in revoke_write:
                grants.add(selector)
                result.errors.append(
                    f"{selector}: write access was NOT revoked; "
                    "native removal failed, so disable it in the client"
                )
            if fresh_install:
                try:
                    # Keep diagnostic files outside the client's plugin discovery paths.
                    failed = _installed(
                        invoke([client, "plugin", "list", "--json"]), plugin, home, client
                    )
                    if failed:
                        backup_root = home / ".repo-template/backups"
                        backup_root.mkdir(parents=True, exist_ok=True)
                        backup = Path(tempfile.mkdtemp(prefix="plugin-", dir=backup_root))
                        shutil.copytree(failed["path"], backup / "content", symlinks=True)
                        result.notes.append(f"{selector}: failed candidate saved at {backup}")
                    invoke(
                        [client, "plugin", "remove" if client == "codex" else "uninstall", plugin]
                    )
                except (OSError, ValueError, subprocess.TimeoutExpired) as cleanup:
                    result.errors.append(
                        f"{selector}: native rollback failed; disable the plugin "
                        f"in the client: {cleanup}"
                    )
            if selector not in previous_grants and not (removing and selector in revoke_write):
                grants.discard(selector)
    if allow_write or revoke_write:
        result.updated.extend(f"optional MCP activation: {name}" for name in allow_write)
        result.removed.extend(
            f"optional MCP activation: {name}" for name in revoke_write if name not in grants
        )
    if not check:
        # Each confirmed install survives an unrelated failure. Native settings reflect the
        # complete batch; hashing them mid-batch would invalidate earlier receipts.
        for selector in result.updated:
            if selector in installed:
                installed[selector]["native_state"] = native_state(home, selector.split(":")[0])
        state["write_mcp"] = sorted(grants)
        atomic_json(state_path(home), state)
    return result


def supplied(agents: Path, home: Path, client: str, kind: str) -> set[str]:
    """Only suppress assets when both native settings and installed content still match."""
    state = read_json(state_path(home))
    catalog = providers(agents)
    found: set[str] = set()
    configuration = native_state(home, client)
    if not configuration:
        return found
    installed = state.get("plugins", {})
    if not isinstance(installed, dict):
        return found
    for selector, evidence in installed.items():
        if not selector.startswith(client + ":") or not isinstance(evidence, dict):
            continue
        provider = catalog.get(selector.split(":", 1)[1], {})
        if (
            evidence.get("provider") != fingerprint(provider)
            or evidence.get("native_state") != configuration
            or tree_digest(Path(evidence.get("path", ""))) != evidence.get("digest")
        ):
            continue
        if provider.get("writeCapable") and selector not in state.get("write_mcp", []):
            continue
        found.update(set(evidence.get(kind, [])) & set(provider.get(kind, [])))
    return found


def filter_servers(agents: Path, home: Path, servers: Mapping[str, Any]) -> dict[str, Any]:
    grants = read_json(state_path(home)).get("write_mcp", [])
    duplicates = {client: supplied(agents, home, client, "mcp") for client in ("codex", "claude")}
    result = {}
    for name, server in servers.items():
        if server.opt_in and name not in grants:
            continue
        clients = frozenset(c for c in server.clients if name not in duplicates[c])
        if clients:
            result[name] = replace(server, clients=clients)
    return result
