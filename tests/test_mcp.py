"""The MCP catalog and where it goes: Claude Code's user scope and ~/.codex/config.toml for
global servers, a repository's .mcp.json and .codex/config.toml for pack servers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from repo_template.mcp import (
    claude_entry,
    codex_toml,
    codex_value,
    deny_rules,
    digest,
    for_packs,
    load_mcp_servers,
    pack_servers,
)
from repo_template.mcp_globals import (
    BLOCK_START,
    sync_claude_mcp,
    sync_codex_mcp,
)
from repo_template.model import Result
from repo_template.repository import update_repository
from repo_template.runner import Completed
from repo_template.scaffold import new_project, read_manifest

ROOT = Path(__file__).resolve().parents[1]
CACHE = "/home/u/.cache/repo-template"
NPX = {
    "scope": "global",
    "command": "npx",
    "args": ["-y", "@x/mcp@1.0.0", "--out", "{cache}/x"],
    "pin": {
        "registry": "npm",
        "package": "@x/mcp",
        "version": "1.0.0",
        "publishedAt": "2026-09-01T10:00:00Z",
    },
    "deny": ["run_unsafe"],
    "codex": {"startup_timeout_sec": 30},
    "source": "https://example.com/x",
    "why": "x",
}
URL = {"scope": "pack", "url": "https://docs.example.com/mcp", "source": "s", "why": "w"}


def _agents(root: Path, servers: Mapping[str, Any], packs: Mapping[str, Any] | None = None) -> Path:
    agents = root / ".agents"
    agents.mkdir(parents=True, exist_ok=True)
    (agents / "mcp-servers.json").write_text(json.dumps({"schema": 1, "servers": servers}))
    if packs is not None:
        (agents / "skill-packs.json").write_text(json.dumps(packs))
    return agents


def test_the_shipped_catalog_is_valid_and_every_deny_reaches_both_clients() -> None:
    servers = load_mcp_servers(ROOT / ".agents")
    pack_servers(ROOT / ".agents", servers)
    portable = json.loads((ROOT / ".agents/claude-settings.json").read_text())["portable"]

    assert deny_rules(servers) <= set(portable["permissions"]["deny"])
    for server in servers.values():
        assert set(server.deny) <= set(codex_value(server, CACHE).get("disabled_tools", []))
    assert portable["enabledPlugins"]["playwright@claude-plugins-official"] is False


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"comand": "npx"}, "unknown keys"),
        ({"url": "https://x"}, "exactly one of 'command' and 'url'"),
        ({"env": {"GH_TOKEN": "x"}}, "keyless"),
        ({"env": {"X": "${HOME}"}}, "no secrets or placeholders"),
        ({"args": ["-y", "@x/mcp@1.0.0", "${X}"]}, "no placeholders"),
        ({"args": ["-y", "@x/mcp@2.0.0"]}, "must run the pinned package@version"),
        ({"pin": None}, "needs a 'pin'"),
        ({"args": ["-y", "@x/mcp@1.0.0", "azmcp"]}, "--read-only"),
        ({"args": ["-y", "@x/mcp@1.0.0", "--dangerously-disable-elicitation"]}, "never allowed"),
        ({"deny": ["a" * 60]}, "longer than 64"),
        ({"why": " "}, "where it comes from and why"),
        ({"scope": "everywhere"}, "global or pack"),
    ],
)
def test_the_catalog_refuses_what_a_server_may_not_be(
    tmp_path: Path, change: dict[str, Any], message: str
) -> None:
    server = {**NPX, **change}
    if server.get("pin") is None:
        server.pop("pin")
    if "url" in change:
        pass  # both command and url
    agents = _agents(tmp_path, {"x": server})

    with pytest.raises(ValueError, match=message):
        load_mcp_servers(agents)


@pytest.mark.parametrize(
    ("packs", "message"),
    [
        ({"p": {"skills": [], "mcp": ["nope"]}}, "not in mcp-servers.json"),
        ({"p": {"skills": [], "mcp": ["x"]}}, "a global server"),
        ({"p": {"skills": [], "mcp": [{"server": "docs", "args": {"-n": ["a"]}}]}}, "--flags"),
    ],
)
def test_packs_use_only_pack_servers(tmp_path: Path, packs: Any, message: str) -> None:
    agents = _agents(tmp_path, {"x": NPX, "docs": URL}, packs)

    with pytest.raises(ValueError, match=message):
        pack_servers(agents, load_mcp_servers(agents))


def test_rendering_differs_by_client_as_each_expands(tmp_path: Path) -> None:
    """Claude Code expands ${NAME:-default}; Codex expands nothing, so it gets literal values."""
    server = load_mcp_servers(_agents(tmp_path, {"x": {**NPX, "env": {"TELEMETRY": "false"}}}))["x"]

    claude, codex = claude_entry(server, CACHE), codex_value(server, CACHE)

    assert claude["args"] == ["-y", "@x/mcp@1.0.0", "--out", f"{CACHE}/x"]
    assert claude["env"] == {
        "TELEMETRY": "${TELEMETRY:-false}",
        "npm_config_before": "2026-09-02T00:00:00Z",  # the cooldown, for first installs too
        "npm_config_cache": f"{CACHE}/npm",
    }
    assert codex["env"]["TELEMETRY"] == "false"
    assert codex["disabled_tools"] == ["run_unsafe"] and codex["startup_timeout_sec"] == 30.0
    assert tomllib.loads(codex_toml("x", codex)) == {"mcp_servers": {"x": codex}}


def test_pack_args_are_the_sorted_union_over_the_packs(tmp_path: Path) -> None:
    azure = {**URL, "url": None, "command": "uvx"}
    del azure["url"]
    azure["args"] = ["--from", "msmcp-azure==1", "azmcp", "--read-only"]
    azure["pin"] = {
        "registry": "pypi",
        "package": "msmcp-azure",
        "version": "1",
        "publishedAt": "2026-09-01T00:00:00Z",
    }
    packs = {
        "a": {"skills": [], "mcp": [{"server": "az", "args": {"--namespace": ["storage"]}}]},
        "b": {
            "skills": [],
            "mcp": [{"server": "az", "args": {"--namespace": ["foundry", "storage"]}}],
        },
    }
    agents = _agents(tmp_path, {"az": azure}, packs)
    servers = load_mcp_servers(agents)

    rendered = claude_entry(
        for_packs(["b", "a"], servers, pack_servers(agents, servers))["az"], CACHE
    )

    assert rendered["args"] == [
        "--exclude-newer", "2026-09-02T00:00:00Z",
        "--from", "msmcp-azure==1", "azmcp", "--read-only",
        "--namespace", "foundry", "--namespace", "storage",
    ]  # fmt: skip


@given(
    args=st.lists(st.text(min_size=1, max_size=12).filter(str.isprintable), max_size=5),
    env=st.dictionaries(
        st.from_regex(r"[A-Z][A-Z0-9_]{0,8}", fullmatch=True).filter(
            lambda k: "KEY" not in k and "TOKEN" not in k
        ),
        st.text(max_size=12).filter(lambda v: v.isprintable() and "${" not in v),
        max_size=3,
    ),
)
def test_the_codex_toml_round_trips(args: list[str], env: dict[str, str]) -> None:
    value = {"command": "npx", "args": args, "startup_timeout_sec": 30.0, "env": env}
    if not env:
        del value["env"]

    assert tomllib.loads(codex_toml("s", value)) == {"mcp_servers": {"s": value}}


# Claude Code's user scope, through a fake of the `claude` CLI.


class FakeClaude:
    def __init__(
        self,
        path: Path,
        servers: dict[str, Any] | None = None,
        *,
        normalize: Callable[[dict[str, Any]], dict[str, Any]] = lambda entry: entry,
        fail: set[tuple[str, str]] | None = None,
        on_path: bool = True,
    ) -> None:
        self.path, self.data, self.normalize = path, dict(servers or {}), normalize
        self.fail, self.on_path, self.calls = fail or set(), on_path, []

    def available(self) -> bool:
        return self.on_path

    def servers(self) -> dict[str, Any]:
        return deepcopy(self.data)

    def add(self, name: str, entry: Mapping[str, Any]) -> Completed:
        self.calls.append(("add", name))
        if ("add", name) in self.fail:  # fails once, like a network error
            self.fail.discard(("add", name))
            return Completed(1, "", "boom")
        if name in self.data:
            return Completed(
                1, "", f"MCP server {name} already exists" if name in self.data else "boom"
            )
        self.data[name] = self.normalize(dict(entry))
        return Completed(0)

    def remove(self, name: str) -> Completed:
        self.calls.append(("remove", name))
        if ("remove", name) in self.fail or name not in self.data:
            return Completed(1, "", "no such server")
        del self.data[name]
        return Completed(0)


def _servers(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    return load_mcp_servers(_agents(tmp_path / "catalog", {"x": {**NPX, **overrides}}))


def _claude(
    tmp_path: Path, claude: FakeClaude, servers: Mapping[str, Any], *, check: bool = False
) -> Result:
    result = Result(tmp_path)
    sync_claude_mcp(
        servers, claude, tmp_path / "home", result, check=check, cache=CACHE, managed=servers
    )
    return result


def test_claude_user_scope_servers_are_added_then_current(tmp_path: Path) -> None:
    servers = _servers(tmp_path)
    claude = FakeClaude(tmp_path / ".claude.json")

    planned = _claude(tmp_path, claude, servers, check=True)
    assert claude.calls == []  # --check runs nothing
    applied = _claude(tmp_path, claude, servers)
    again = _claude(tmp_path, claude, servers)

    assert planned.created == applied.created == [f"{claude.path} mcpServers.x"]
    assert claude.data["x"] == claude_entry(servers["x"], CACHE)
    assert not again.needs_attention and claude.calls == [("add", "x")]


def test_the_claude_config_is_backed_up_before_its_first_change(tmp_path: Path) -> None:
    servers = _servers(tmp_path)
    claude = FakeClaude(tmp_path / ".claude.json")
    claude.path.write_text('{"mcpServers": {}}\n')
    home = tmp_path / "home"

    sync_claude_mcp(
        servers, claude, home, Result(tmp_path), check=False, cache=CACHE, managed=servers,
        stamp="s1",
    )  # fmt: skip
    sync_claude_mcp(
        servers, claude, home, Result(tmp_path), check=False, cache=CACHE, managed=servers,
        stamp="s2",
    )  # fmt: skip

    backup = home / ".repo-template/backups/s1/.claude.json"
    assert backup.read_text() == '{"mcpServers": {}}\n'
    assert backup.stat().st_mode & 0o777 == 0o600
    assert not (home / ".repo-template/backups/s2").exists()  # nothing to change, no backup


def test_a_new_pin_replaces_an_owned_server_and_a_hand_edit_is_kept(tmp_path: Path) -> None:
    claude = FakeClaude(tmp_path / ".claude.json")
    _claude(tmp_path, claude, _servers(tmp_path))
    bumped = _servers(
        tmp_path / "b",
        args=["-y", "@x/mcp@1.1.0", "--out", "{cache}/x"],
        pin={**NPX["pin"], "version": "1.1.0"},
    )

    replaced = _claude(tmp_path, claude, bumped)
    claude.data["x"]["args"].append("--mine")
    kept = _claude(
        tmp_path,
        claude,
        _servers(
            tmp_path / "c", args=["-y", "@x/mcp@1.2.0"], pin={**NPX["pin"], "version": "1.2.0"}
        ),
    )
    quiet = _claude(
        tmp_path,
        claude,
        _servers(
            tmp_path / "d", args=["-y", "@x/mcp@1.2.0"], pin={**NPX["pin"], "version": "1.2.0"}
        ),
    )

    assert replaced.updated == [f"{claude.path} mcpServers.x"]
    assert kept.preserved == [f"{claude.path} mcpServers.x (configured by hand; kept)"]
    assert quiet.preserved == []  # reported once
    assert "--mine" in claude.data["x"]["args"]


def test_a_server_removed_on_the_machine_stays_removed(tmp_path: Path) -> None:
    servers = _servers(tmp_path)
    claude = FakeClaude(tmp_path / ".claude.json")
    _claude(tmp_path, claude, servers)
    del claude.data["x"]  # `claude mcp remove x`

    first = _claude(tmp_path, claude, servers)
    second = _claude(tmp_path, claude, servers)

    assert "x" not in claude.data
    assert first.preserved == [f"{claude.path} mcpServers.x (removed on this machine; kept)"]
    assert second.preserved == []


def test_a_server_dropped_from_the_catalog_is_removed_if_unchanged(tmp_path: Path) -> None:
    claude = FakeClaude(tmp_path / ".claude.json")
    _claude(tmp_path, claude, _servers(tmp_path))

    result = _claude(tmp_path, claude, {})

    assert result.removed == [f"{claude.path} mcpServers.x"] and claude.data == {}


def test_a_failed_replace_puts_the_old_entry_back(tmp_path: Path) -> None:
    claude = FakeClaude(tmp_path / ".claude.json")
    _claude(tmp_path, claude, _servers(tmp_path))
    old = deepcopy(claude.data["x"])
    claude.fail = {("add", "x")}

    result = _claude(
        tmp_path,
        claude,
        _servers(
            tmp_path / "b",
            args=["-y", "@x/mcp@1.1.0", "--out", "{cache}/x"],
            pin={**NPX["pin"], "version": "1.1.0"},
        ),
    )
    claude.fail = set()

    assert result.errors and claude.data["x"] == old


def test_claude_normalizing_an_entry_differently_causes_no_churn(tmp_path: Path) -> None:
    """A later Claude Code may store entries in another form; that isn't a hand edit."""
    claude = FakeClaude(tmp_path / ".claude.json", normalize=lambda entry: {**entry, "extra": 1})
    servers = _servers(tmp_path)
    _claude(tmp_path, claude, servers)
    calls = list(claude.calls)

    again = _claude(tmp_path, claude, servers)

    assert not again.needs_attention and claude.calls == calls


def test_no_claude_on_path_is_a_note_and_a_duplicate_gets_its_removal_command(
    tmp_path: Path,
) -> None:
    servers = _servers(tmp_path)
    claude = FakeClaude(
        tmp_path / ".claude.json",
        {"old-x": {"type": "stdio", "command": "npx", "args": ["@x/mcp@0.9.0"]}},
        on_path=False,
    )

    result = _claude(tmp_path, claude, servers)

    assert any("no `claude` on PATH" in note for note in result.notes)
    assert any("`claude mcp remove old-x --scope user`" in note for note in result.notes)
    assert "old-x" in claude.data


# ~/.codex/config.toml


FOREIGN = """model = "gpt-5"

[mcp_servers.mine]
command = "mine"

[projects."/work/a"]
trust_level = "trusted"
"""


def _codex(tmp_path: Path, servers: Mapping[str, Any], *, check: bool = False) -> Result:
    result = Result(tmp_path)
    sync_codex_mcp(
        servers, tmp_path / "home/.codex/config.toml", tmp_path / "home", result,
        check=check, stamp="s", cache=CACHE, managed=servers,
    )  # fmt: skip
    return result


def _config(tmp_path: Path, text: str = FOREIGN) -> Path:
    path = tmp_path / "home/.codex/config.toml"
    path.parent.mkdir(parents=True)
    path.write_text(text)
    path.chmod(0o600)
    return path


def test_codex_servers_are_added_without_touching_anything_else(tmp_path: Path) -> None:
    path = _config(tmp_path)
    servers = _servers(tmp_path)

    applied = _codex(tmp_path, servers)
    again = _codex(tmp_path, servers)

    data = tomllib.loads(path.read_text())
    assert data["mcp_servers"]["x"] == codex_value(servers["x"], CACHE)
    assert data["mcp_servers"]["mine"] == {"command": "mine"}
    assert data["projects"] == {"/work/a": {"trust_level": "trusted"}} and data["model"] == "gpt-5"
    assert applied.created == [f"{path} mcp_servers.x"] and not again.needs_attention
    assert path.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "home/.repo-template/backups/s/.codex/config.toml").read_text() == FOREIGN


def test_codex_rewriting_the_file_doesnt_lose_ownership(tmp_path: Path) -> None:
    """`codex mcp add` drops comments and writes 30 as 30.0; ownership is by digest."""
    path = _config(tmp_path)
    _codex(tmp_path, _servers(tmp_path))
    rewritten = path.read_text().replace(BLOCK_START + "\n", "").replace("30.0", "30")
    path.write_text(rewritten)

    bumped = _codex(tmp_path, _servers(tmp_path / "b", deny=["other"]))

    assert bumped.updated == [f"{path} mcp_servers.x"]
    assert tomllib.loads(path.read_text())["mcp_servers"]["x"]["disabled_tools"] == ["other"]


def test_a_codex_edit_that_would_touch_more_is_refused(tmp_path: Path) -> None:
    """A server written inline can't be edited as a table: nothing is written."""
    path = _config(tmp_path, 'mcp_servers = { x = { command = "old" } }\n')
    claim = {
        "version": 1,
        "path": str(path),
        "owned": {"x": {"stored": digest({"command": "old"}), "rendered": "r"}},
        "kept": {},
        "removed": {},
    }
    state = tmp_path / "home/.repo-template/globals-state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"codex_mcp": claim}))

    result = _codex(tmp_path, _servers(tmp_path))

    assert any("couldn't edit it safely" in error for error in result.errors), result
    assert path.read_text() == 'mcp_servers = { x = { command = "old" } }\n'


def test_codex_invalid_toml_and_a_missing_codex_home(tmp_path: Path) -> None:
    servers = _servers(tmp_path)
    assert any("Codex MCP servers: skipped" in n for n in _codex(tmp_path, servers).notes)
    _config(tmp_path, "not = [toml\n")

    assert any("cannot read" in e for e in _codex(tmp_path, servers).errors)


@pytest.mark.skipif(shutil.which("codex") is None, reason="needs codex")
def test_codex_itself_reads_the_servers_written(tmp_path: Path) -> None:
    path = _config(tmp_path)
    _codex(tmp_path, load_mcp_servers(ROOT / ".agents"))

    done = subprocess.run(
        ["codex", "mcp", "list", "--json"],
        capture_output=True, text=True, timeout=120, check=False,
        env={**os.environ, "CODEX_HOME": str(path.parent), "HOME": str(tmp_path / "home")},
    )  # fmt: skip

    names = {server["name"] for server in json.loads(done.stdout)}
    assert {"playwright", "huggingface", "microsoft-learn", "mine"} <= names, done.stderr


# A repository's pack servers.


def _repository(tmp_path: Path, packs: list[str] | None = None) -> tuple[Path, Path]:
    catalog = tmp_path / "standards/.agents"
    for name in ("lc-one",):
        (catalog / "packs" / name).mkdir(parents=True)
        (catalog / "packs" / name / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: x\n---\n"
        )
    _agents(
        tmp_path / "standards",
        {
            "docs": URL,
            "codex-only": {**URL, "url": "https://c.example.com/mcp", "clients": ["codex"]},
        },
        {
            "lc": {"description": "LC", "skills": ["lc-one"], "mcp": ["docs", "codex-only"]},
            "other": {"description": "O", "skills": []},
        },
    )
    root = tmp_path / "service"
    new_project(root, name="service", description="S.", python_version="3.12")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "core.excludesFile", os.devnull], check=True)
    return root, catalog


def _update(root: Path, catalog: Path, **kwargs: Any) -> Result:
    return update_repository(root, hooks=False, lock=False, agents_dir=catalog, **kwargs)


def test_a_pack_brings_its_servers_and_records_them(tmp_path: Path) -> None:
    root, catalog = _repository(tmp_path)

    planned = _update(root, catalog, packs=["lc"], check=True)
    applied = _update(root, catalog, packs=["lc"])
    current = _update(root, catalog, check=True)

    project = json.loads((root / ".mcp.json").read_text())
    assert project == {
        "mcpServers": {"docs": {"type": "http", "url": "https://docs.example.com/mcp"}}
    }
    assert read_manifest(root)["mcp_servers"] == {"docs": digest(project["mcpServers"]["docs"])}
    codex = tomllib.loads((root / ".codex/config.toml").read_text())
    assert set(codex["mcp_servers"]) == {"docs", "codex-only"}
    assert ".mcp.json mcpServers.docs" in planned.created
    assert planned.created == applied.created
    assert not current.needs_attention, current
    assert any("trust" in note for note in applied.notes)
    text = (root / ".mcp.json").read_text() + (root / ".codex/config.toml").read_text()
    assert "enableAllProjectMcpServers" not in text and "enabledMcpjsonServers" not in text


def test_dropping_the_pack_removes_its_servers_and_files(tmp_path: Path) -> None:
    root, catalog = _repository(tmp_path)
    _update(root, catalog, packs=["lc"])
    manifest = json.loads((root / ".repo-template.json").read_text())
    manifest["skill_packs"] = ["other"]
    (root / ".repo-template.json").write_text(json.dumps(manifest))

    result = _update(root, catalog)

    assert ".mcp.json mcpServers.docs" in result.removed
    assert not (root / ".mcp.json").exists() and not (root / ".codex").exists()
    assert "mcp_servers" not in read_manifest(root)


def test_an_edited_entry_and_other_servers_are_kept(tmp_path: Path) -> None:
    root, catalog = _repository(tmp_path)
    _update(root, catalog, packs=["lc"])
    project = json.loads((root / ".mcp.json").read_text())
    project["mcpServers"]["docs"]["url"] = "https://mine.example.com/mcp"
    project["mcpServers"]["team"] = {"type": "http", "url": "https://team.example.com/mcp"}
    (root / ".mcp.json").write_text(json.dumps(project))
    manifest = json.loads((root / ".repo-template.json").read_text())
    manifest["skill_packs"] = ["other"]
    (root / ".repo-template.json").write_text(json.dumps(manifest))

    result = _update(root, catalog)

    project = json.loads((root / ".mcp.json").read_text())
    assert project["mcpServers"]["docs"]["url"] == "https://mine.example.com/mcp"
    assert "team" in project["mcpServers"]
    assert any("edited; kept" in note for note in result.notes)


def test_an_entry_edited_while_the_pack_is_used_is_preserved(tmp_path: Path) -> None:
    root, catalog = _repository(tmp_path)
    _update(root, catalog, packs=["lc"])
    project = json.loads((root / ".mcp.json").read_text())
    project["mcpServers"]["docs"]["url"] = "https://mine.example.com/mcp"
    (root / ".mcp.json").write_text(json.dumps(project))

    result = _update(root, catalog)

    assert result.preserved == [".mcp.json mcpServers.docs (edited in this repository; kept)"]
    assert json.loads((root / ".mcp.json").read_text())["mcpServers"]["docs"]["url"].startswith(
        "https://mine"
    )


def test_a_codex_block_edited_by_hand_is_preserved(tmp_path: Path) -> None:
    root, catalog = _repository(tmp_path)
    _update(root, catalog, packs=["lc"])
    path = root / ".codex/config.toml"
    path.write_text(
        path.read_text().replace("https://docs.example.com/mcp", "https://x.example.com/mcp")
    )

    result = _update(root, catalog)

    assert result.preserved == [".codex/config.toml (edited inside the repo-template block; kept)"]


def test_project_owned_files_are_left_alone(tmp_path: Path) -> None:
    root, catalog = _repository(tmp_path)
    manifest = json.loads((root / ".repo-template.json").read_text())
    manifest["project_owned"] = [".mcp.json", ".codex/config.toml"]
    (root / ".repo-template.json").write_text(json.dumps(manifest))

    _update(root, catalog, packs=["lc"])

    assert not (root / ".mcp.json").exists() and not (root / ".codex/config.toml").exists()


def test_a_codex_file_git_would_commit_isnt_written(tmp_path: Path) -> None:
    """It holds this machine's paths: only an ignored .codex/config.toml is written. (The
    python-uv baseline always ignores .codex/; a packs-only repository may not.)"""
    from repo_template.mcp_project import apply_project_mcp, plan_project_mcp

    root = tmp_path / "plain"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "core.excludesFile", os.devnull], check=True)
    servers = load_mcp_servers(_agents(tmp_path / "standards", {"docs": URL}))
    plan = plan_project_mcp(root, servers, {}, owned=set(), removals=True, cache=CACHE)
    planned, result = Result(root), Result(root)

    apply_project_mcp(root, plan, planned, check=True)
    apply_project_mcp(root, plan, result, check=False)

    expected = (
        ".codex/config.toml (Git doesn't ignore it here; not written, since it would hold this "
        "machine's paths)"
    )
    assert planned.preserved == result.preserved == [expected]
    assert not (root / ".codex/config.toml").exists()
    assert (root / ".mcp.json").is_file()  # the committed file is fine to write
