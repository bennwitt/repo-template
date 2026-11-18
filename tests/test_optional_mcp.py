"""Optional pack servers: a write-capable server a pack offers, which reaches a repository only
on a machine granted it, and then only that machine's own config, never the committed one."""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
from test_personal import FakeClaude  # Claude Code's local scope, in memory

from repo_template.catalog import _check_mcp, _Problems
from repo_template.mcp import ask_rules, deny_rules, load_mcp_servers, pack_servers
from repo_template.repository import create_repository, update_repository
from repo_template.scaffold import new_project, read_manifest
from repo_template.standards import sync_globals

ROOT = Path(__file__).resolve().parents[1]
PIN = {
    "registry": "npm",
    "package": "@x/mcp",
    "version": "1.0.0",
    "publishedAt": "2026-09-01T10:00:00Z",
}
SAFE = {
    "scope": "pack",
    "command": "npx",
    "args": ["-y", "@x/mcp@1.0.0", "--out", "{cache}/x"],
    "pin": PIN,
    "deny": ["run_unsafe"],
    "source": "s",
    "why": "w",
}
UNSAFE = {
    **SAFE,
    "args": ["-y", "@x/mcp@1.0.0", "--out", "{cache}/x-unsafe"],
    "deny": [],
    "allow": ["run_unsafe"],
    "optIn": True,
    "access": "write",
}
PORTABLE = {
    "permissions": {
        "deny": ["mcp__browser__run_unsafe"],
        "ask": ["mcp__browser-unsafe__run_unsafe"],
    }
}


def _catalog(root: Path, servers: dict[str, Any] | None = None) -> Path:
    agents = root / ".agents"
    (agents / "packs/browser-skill").mkdir(parents=True)
    (agents / "packs/browser-skill/SKILL.md").write_text("---\nname: browser-skill\n---\n")
    (agents / "skill-packs.json").write_text(
        json.dumps(
            {
                "browser": {
                    "description": "B",
                    "skills": ["browser-skill"],
                    "mcp": ["browser", "browser-unsafe"],
                }
            }
        )
    )
    catalog = servers if servers is not None else {"browser": SAFE, "browser-unsafe": UNSAFE}
    (agents / "mcp-servers.json").write_text(json.dumps({"schema": 1, "servers": catalog}))
    (agents / "claude-settings.json").write_text(json.dumps({"portable": PORTABLE, "defaults": {}}))
    return agents


def _grant(home: Path, *names: str) -> None:
    state = home / ".repo-template/capabilities.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"write_mcp": list(names)}))


def _team_repo(root: Path) -> Path:
    new_project(root, name=root.name, description="S.", python_version="3.12")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "core.excludesFile", os.devnull], check=True)
    return root


def _update(root: Path, agents: Path, claude: FakeClaude, home: Path, **kwargs: Any) -> Any:
    return update_repository(
        root, hooks=False, lock=False, agents_dir=agents, claude=claude, home=home, **kwargs
    )


@pytest.fixture
def team(tmp_path: Path) -> tuple[Path, Path, FakeClaude, Path]:
    agents = _catalog(tmp_path / "standards")
    root = _team_repo(tmp_path / "service")
    home = tmp_path / "home"
    home.mkdir()
    return agents, root, FakeClaude(home / ".claude.json"), home


def test_without_a_grant_a_repository_gets_only_the_safe_server(
    team: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = team

    result = _update(root, agents, claude, home, packs=["browser"])

    assert list(json.loads((root / ".mcp.json").read_text())["mcpServers"]) == ["browser"]
    assert list(tomllib.loads((root / ".codex/config.toml").read_text())["mcp_servers"]) == [
        "browser"
    ]
    assert claude.calls == [] and not any("local-scope" in note for note in result.notes)


def test_a_grant_adds_the_unsafe_server_to_this_machines_config_only(
    team: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = team
    _update(root, agents, claude, home, packs=["browser"])
    committed = (root / ".mcp.json").read_text(), read_manifest(root)
    _grant(home, "browser-unsafe")

    planned = _update(root, agents, claude, home, check=True)
    assert any("browser-unsafe" in line for line in planned.created) and claude.data == {}
    _update(root, agents, claude, home)

    assert ((root / ".mcp.json").read_text(), read_manifest(root)) == committed
    assert list(claude.data) == ["browser-unsafe"]
    assert claude.data["browser-unsafe"]["args"][-1].endswith("/x-unsafe")
    codex = tomllib.loads((root / ".codex/config.toml").read_text())["mcp_servers"]
    assert codex["browser"]["disabled_tools"] == ["run_unsafe"]
    assert "disabled_tools" not in codex["browser-unsafe"]
    assert not _update(root, agents, claude, home, check=True).needs_attention


def test_revoking_the_grant_takes_the_unsafe_server_out_again(
    team: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = team
    _grant(home, "browser-unsafe")
    _update(root, agents, claude, home, packs=["browser"])
    assert list(claude.data) == ["browser-unsafe"]
    _grant(home)

    result = _update(root, agents, claude, home)

    assert claude.data == {} and any("browser-unsafe" in line for line in result.removed)
    assert "browser-unsafe" not in (root / ".codex/config.toml").read_text()
    assert list(json.loads((root / ".mcp.json").read_text())["mcpServers"]) == ["browser"]


def test_a_new_repository_on_a_granted_machine_gets_it_locally(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    home = tmp_path / "home"
    _grant(home, "browser-unsafe")
    claude = FakeClaude(home / ".claude.json")

    create_repository(
        tmp_path / "fresh", name="fresh", description="F.", python_version="3.12", git=False,
        lock=False, packs=["browser"], agents_dir=agents, claude=claude, home=home,
    )  # fmt: skip

    assert list(json.loads((tmp_path / "fresh/.mcp.json").read_text())["mcpServers"]) == ["browser"]
    assert list(claude.data) == ["browser-unsafe"]


def test_globals_never_installs_a_pack_server_on_its_own(tmp_path: Path) -> None:
    standards = tmp_path / "standards"
    _catalog(standards)
    (standards / ".agents/skills").mkdir()
    home = tmp_path / "home"
    _grant(home, "browser-unsafe")
    claude = FakeClaude(home / ".claude.json")

    sync_globals(standards, home=home, claude=claude)

    codex = home / ".codex/config.toml"
    assert claude.data == {}
    assert not codex.exists() or "browser" not in codex.read_text()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"browser-unsafe": {**UNSAFE, "optIn": False}}, "requires explicit optIn"),
        ({"browser-unsafe": {**UNSAFE, "access": "read"}}, "only an optIn, write-capable"),
        ({"browser-unsafe": {**UNSAFE, "deny": ["run_unsafe"]}}, "both allowed and denied"),
        ({"browser": {**SAFE, "allow": ["run_unsafe"]}}, "only an optIn, write-capable"),
    ],
)
def test_allow_belongs_to_optional_write_servers(
    tmp_path: Path, change: dict[str, Any], message: str
) -> None:
    agents = _catalog(tmp_path, {"browser": SAFE, "browser-unsafe": UNSAFE, **change})

    with pytest.raises(ValueError, match=message):
        load_mcp_servers(agents)


def test_an_allowed_tool_is_denied_per_server_and_asked_before_each_call(tmp_path: Path) -> None:
    other = {**SAFE, "args": ["-y", "@x/mcp@1.0.0"], "deny": ["run_unsafe", "submit"]}
    servers = load_mcp_servers(
        _catalog(tmp_path, {"browser": SAFE, "browser-unsafe": UNSAFE, "other": other})
    )

    assert deny_rules(servers) == {
        "mcp__browser__run_unsafe",
        "mcp__other__run_unsafe",
        "mcp__*__submit",
    }
    assert ask_rules(servers) == {"mcp__browser-unsafe__run_unsafe"}


@pytest.mark.parametrize(
    ("permissions", "message"),
    [
        (
            {"deny": ["mcp__browser__run_unsafe"], "ask": []},
            "add the rule to portable permissions.ask",
        ),
        (
            {
                "deny": ["mcp__browser__run_unsafe", "mcp__*__run_unsafe"],
                "ask": PORTABLE["permissions"]["ask"],
            },
            "denies the tool for the optional server that allows it too",
        ),
    ],
)
def test_the_catalog_check_keeps_the_allowed_tool_reachable_and_asked(
    tmp_path: Path, permissions: dict[str, list[str]], message: str
) -> None:
    agents = _catalog(tmp_path)
    (agents / "claude-settings.json").write_text(
        json.dumps({"portable": {"permissions": permissions}, "defaults": {}})
    )
    problems = _Problems()

    _check_mcp(tmp_path, problems)

    assert any(message in error for error in problems.errors), problems.errors


def test_the_shipped_unsafe_playwright_server_matches_the_safe_one() -> None:
    servers = load_mcp_servers(ROOT / ".agents")
    refs = pack_servers(ROOT / ".agents", servers)
    safe, unsafe = servers["playwright"], servers["playwright-unsafe"]
    portable = json.loads((ROOT / ".agents/claude-settings.json").read_text())["portable"]

    assert ("playwright-unsafe", {}) in refs["playwright"]
    assert (unsafe.scope, unsafe.opt_in, unsafe.access) == ("pack", True, "write")
    assert unsafe.allow == ("browser_run_code_unsafe",) and not unsafe.deny
    assert unsafe.pin == safe.pin
    assert [a for a in unsafe.args if "{cache}" not in a] == [
        a for a in safe.args if "{cache}" not in a
    ]  # the same flags and capabilities; only its output folder differs
    assert "mcp__*__browser_run_code_unsafe" not in portable["permissions"]["deny"]
    assert "mcp__playwright__browser_run_code_unsafe" in portable["permissions"]["deny"]
    assert "mcp__playwright-unsafe__browser_run_code_unsafe" in portable["permissions"]["ask"]
    assert not any(
        "stagehand" in pack for pack, used in refs.items() if ("playwright-unsafe", {}) in used
    )


def test_the_shipped_figma_servers_split_reads_from_writes() -> None:
    servers = load_mcp_servers(ROOT / ".agents")
    refs = pack_servers(ROOT / ".agents", servers)
    read, write = servers["figma"], servers["figma-write"]
    portable = json.loads((ROOT / ".agents/claude-settings.json").read_text())["portable"]
    denied, asked = set(portable["permissions"]["deny"]), set(portable["permissions"]["ask"])
    weave = {tool for tool in read.deny if tool.startswith("weave_")}

    assert [name for name, _ in refs["figma"]] == ["figma", "figma-write"]
    assert read.url == write.url == "https://mcp.figma.com/mcp"
    assert (read.scope, read.opt_in, read.access) == ("pack", False, "read")
    assert (write.scope, write.opt_in, write.access) == ("pack", True, "write")
    assert set(read.deny) - weave == set(write.allow) and len(write.allow) == 15
    assert set(write.deny) == weave and weave
    assert read.enabled_tools is not None  # Codex gets an allowlist, so new tools stay off
    assert not set(read.enabled_tools) & (set(write.allow) | weave)
    for tool in write.allow:
        assert f"mcp__figma__{tool}" in denied
        assert f"mcp__figma-write__{tool}" in asked
        assert f"mcp__plugin_figma_figma__{tool}" in asked  # Figma's plugin, installed by hand
    assert {f"mcp__*__{tool}" for tool in weave} <= denied


def test_a_personal_repository_gets_both_servers_locally_on_a_granted_machine(
    tmp_path: Path,
) -> None:
    from test_personal import _status
    from test_personal import _team_repo as someone_elses_repo

    agents = _catalog(tmp_path / "standards")
    root = someone_elses_repo(tmp_path / "team")
    home = tmp_path / "home"
    _grant(home, "browser-unsafe")
    claude = FakeClaude(home / ".claude.json")

    update_repository(
        root, agents_dir=agents, claude=claude, home=home, packs=["browser"], personal=True
    )

    assert sorted(claude.data) == ["browser", "browser-unsafe"]
    assert _status(root) == "" and not (root / ".mcp.json").exists()


def test_the_shipped_mongodb_server_is_pinned_and_read_only() -> None:
    servers = load_mcp_servers(ROOT / ".agents")
    refs = pack_servers(ROOT / ".agents", servers)
    raw = json.loads((ROOT / ".agents/mcp-servers.json").read_text())["servers"]["mongodb"]
    mongodb = servers["mongodb"]

    assert [name for name, _ in refs["mongodb"]] == ["mongodb"]
    assert (mongodb.scope, mongodb.opt_in, mongodb.access) == ("pack", False, "read")
    assert mongodb.command == "npx"
    assert "--readOnly" in mongodb.args  # only read, connect and metadata tools are registered
    assert mongodb.args[mongodb.args.index("--telemetry") + 1] == "disabled"
    assert mongodb.pin is not None and mongodb.pin.package == "mongodb-mcp-server"
    assert f"mongodb-mcp-server@{mongodb.pin.version}" in mongodb.args
    assert "env" not in raw  # the connection string stays on the machine
    assert "MDB_MCP_CONNECTION_STRING" in raw["codex"]["env_vars"]
