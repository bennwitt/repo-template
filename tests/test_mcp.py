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
    ("server", "message"),
    [
        ({**URL, "url": "http://docs.example.com/mcp"}, "https://"),
        ({**URL, "url": "https://user:pw@docs.example.com/mcp"}, "no credentials"),
        ({**URL, "url": "https://docs.example.com/mcp?key=x"}, "no credentials, query"),
        ({**URL, "env": {"X": "1"}}, "a url server has no 'env'"),
        ({**URL, "pin": NPX["pin"]}, "a url server has no 'pin'"),
        (
            {**NPX, "command": "uvx", "args": ["--with", "evil", "--from", "x==1", "x"],
             "pin": {**NPX["pin"], "registry": "pypi", "package": "x", "version": "1"}},
            "must run the pinned package first",
        ),
        (
            {**NPX, "command": "uvx", "args": ["--from", "x==1"],
             "pin": {**NPX["pin"], "registry": "pypi", "package": "x", "version": "1"}},
            "must run the pinned package first",
        ),
        (
            {**NPX, "command": "uvx", "args": ["x@latest"],
             "pin": {**NPX["pin"], "registry": "pypi", "package": "x", "version": "1"}},
            "must run the pinned package first",
        ),
    ],
)  # fmt: skip
def test_the_catalog_refuses_urls_and_uvx_runs_it_cant_vouch_for(
    tmp_path: Path, server: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        load_mcp_servers(_agents(tmp_path, {"x": server}))


@pytest.mark.parametrize(
    "args", [["--from", "msmcp-azure==3.0.0", "azmcp", "server", "start"], ["x==1"], ["x@1"]]
)
def test_uvx_runs_its_pin_in_any_of_the_forms_uv_takes(tmp_path: Path, args: list[str]) -> None:
    package, version = ("msmcp-azure", "3.0.0") if args[0] == "--from" else ("x", "1")
    if "azmcp" in args:
        args = [*args, "--read-only"]
    server = {
        **NPX,
        "command": "uvx",
        "args": args,
        "pin": {**NPX["pin"], "registry": "pypi", "package": package, "version": version},
    }

    assert load_mcp_servers(_agents(tmp_path, {"x": server}))["x"].args == tuple(args)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"comand": "npx"}, "unknown keys"),
        ({"url": "https://x"}, "exactly one of 'command' and 'url'"),
        ({"env": {"GH_TOKEN": "x"}}, "keyless"),
        ({"env": {"X": "${HOME}"}}, "no secrets or placeholders"),
        ({"args": ["-y", "@x/mcp@1.0.0", "${X}"]}, "no placeholders"),
        ({"args": ["-y", "@x/mcp@2.0.0"]}, "must run the pinned package first"),
        ({"args": ["-y", "other@1", "@x/mcp@1.0.0"]}, "must run the pinned package first"),
        ({"args": ["-y", "-p", "@x/mcp@1.0.0", "other"]}, "must run the pinned package first"),
        ({"pin": None}, "needs a 'pin'"),
        ({"command": "bash", "args": ["-c", "x"]}, "'command' is npx or uvx"),
        ({"pin": {**NPX["pin"], "registry": "pypi"}}, "pin is on npm"),
        ({"pin": {**NPX["pin"], "publishedAt": "2026-09-01T10:00:00"}}, "needs a time zone"),
        ({"pin": {**NPX["pin"], "publishedAt": "yesterday"}}, "ISO-8601"),
        ({"pin": {**NPX["pin"], "extra": 1}}, "'pin' takes"),
        ({"codex": {"sandbox": "off"}}, "'codex' takes"),
        ({"clients": ["cursor"]}, "claude and/or codex"),
        ({"args": ["-y", "@x/mcp@1.0.0", "--api-key", "x"]}, "no secrets in args"),
        ({"args": ["-y", "@x/mcp@1.0.0", "hf_abcdefghijklmnop"]}, "no secrets in args"),
        ({"env": {"GITHUB_PAT": "x"}}, "keyless"),
        ({"env": {"X_AUTH": "x"}}, "keyless"),
        ({"env": {"X": "a}b"}}, "no secrets or placeholders"),
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
    azure["packArgs"] = ["--namespace"]
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
        present: bool = True,
        lands: bool = True,
    ) -> None:
        self.path, self.data, self.normalize = path, dict(servers or {}), normalize
        self.fail, self.on_path, self.calls = fail or set(), on_path, []
        self.present, self.lands = present, lands  # the file exists; an add reaches it

    def available(self) -> bool:
        return self.on_path

    def exists(self) -> bool:
        return self.present

    def servers(self) -> dict[str, Any]:
        return deepcopy(self.data)

    def add(self, name: str, entry: Mapping[str, Any]) -> Completed:
        self.calls.append(("add", name))
        if ("add", name) in self.fail:  # fails once, like a network error
            self.fail.discard(("add", name))
            return Completed(1, "", "boom")
        if ("add-twice", name) in self.fail:
            self.fail = {("add", name)}
            return Completed(1, "", "boom")
        if not self.lands:  # written to another file
            return Completed(0)
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
    sync_claude_mcp(servers, claude, tmp_path / "home", result, check=check, cache=CACHE)
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
        servers, claude, home, Result(tmp_path), check=False, cache=CACHE,
        stamp="s1",
    )  # fmt: skip
    sync_claude_mcp(
        servers, claude, home, Result(tmp_path), check=False, cache=CACHE,
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


@pytest.mark.parametrize("check", [True, False])
def test_no_claude_on_path_is_a_note_in_check_and_update_alike(tmp_path: Path, check: bool) -> None:
    claude = FakeClaude(tmp_path / ".claude.json", on_path=False)

    result = _claude(tmp_path, claude, _servers(tmp_path), check=check)

    assert result.notes == ["Claude Code's user-scope MCP servers: skipped (no `claude` on PATH)"]
    assert not result.needs_attention and claude.calls == []


def test_a_duplicate_of_a_server_this_client_gets_has_its_removal_command(tmp_path: Path) -> None:
    claude = FakeClaude(
        tmp_path / ".claude.json",
        {
            "old-x": {"type": "stdio", "command": "npx", "args": ["@x/mcp@0.9.0"]},
            "my-docs": {"type": "http", "url": URL["url"]},  # a pack server's: not reported
        },
    )

    result = _claude(tmp_path, claude, _servers(tmp_path))

    assert result.notes == [
        f"{claude.path} mcpServers.old-x runs the x server repo-template installs; remove it "
        f"with `claude mcp remove old-x --scope user`"
    ]
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
        check=check, stamp="s", cache=CACHE,
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


def _inline(value: Mapping[str, Any]) -> str:
    parts = (
        f"{key} = {_inline(item) if isinstance(item, dict) else json.dumps(item)}"
        for key, item in value.items()
    )
    return "{ " + ", ".join(parts) + " }"


@pytest.mark.parametrize("form", ["[mcp_servers]\nx = {}\n", "mcp_servers.x = {}\n"])
def test_a_server_not_written_as_its_own_table_is_never_taken_over(
    tmp_path: Path, form: str
) -> None:
    """remove_tables can rewrite only [mcp_servers.<name>]: an inline table or dotted keys with
    the same value isn't adopted, so later writes can't collide with it."""
    servers = _servers(tmp_path)
    value = codex_value(servers["x"], CACHE)
    path = _config(tmp_path, form.format(_inline(value)))
    other = load_mcp_servers(_agents(tmp_path / "y", {"y": {**URL, "scope": "global"}}))

    first = _codex(tmp_path, {**servers, **other})
    second = _codex(tmp_path, {**_servers(tmp_path / "b", deny=["other"]), **other})

    assert first.errors == [] and first.created == [f"{path} mcp_servers.y"]
    assert second.errors == []
    assert second.preserved == [f"{path} mcp_servers.x (configured by hand; kept)"]
    assert tomllib.loads(path.read_text())["mcp_servers"]["x"] == value


def test_a_quoted_table_name_is_rewritten_like_any_table(tmp_path: Path) -> None:
    servers = _servers(tmp_path)
    path = _config(
        tmp_path,
        codex_toml("x", codex_value(servers["x"], CACHE))
        .replace("[mcp_servers.x]", "[mcp_servers.'x']")
        .replace("[mcp_servers.x.env]", '[mcp_servers."x".env]'),
    )

    _codex(tmp_path, servers)
    bumped = _codex(tmp_path, _servers(tmp_path / "b", deny=["other"]))

    assert bumped.errors == [] and bumped.updated == [f"{path} mcp_servers.x"]
    assert tomllib.loads(path.read_text())["mcp_servers"]["x"]["disabled_tools"] == ["other"]


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
    from repo_template.mcp_project import apply_codex_mcp, plan_codex_mcp

    root = tmp_path / "plain"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "core.excludesFile", os.devnull], check=True)
    servers = load_mcp_servers(_agents(tmp_path / "standards", {"docs": URL}))
    plan = plan_codex_mcp(root, servers, owned=set(), removals=True, cache=CACHE)
    planned, result = Result(root), Result(root)

    apply_codex_mcp(root, plan, planned, check=True)
    apply_codex_mcp(root, plan, result, check=False)

    expected = (
        ".codex/config.toml (Git doesn't ignore it here; not written, since it would hold this "
        "machine's paths)"
    )
    assert planned.preserved == result.preserved == [expected]
    assert not (root / ".codex/config.toml").exists()


# Review findings for the global servers.


def test_a_replace_whose_restore_fails_too_is_added_again_next_time(tmp_path: Path) -> None:
    claude = FakeClaude(tmp_path / ".claude.json")
    _claude(tmp_path, claude, _servers(tmp_path))
    claude.fail = {("add-twice", "x")}
    bumped = load_mcp_servers(
        _agents(
            tmp_path / "c",
            {
                "x": {
                    **NPX,
                    "args": ["-y", "@x/mcp@1.0.1"],
                    "pin": {**NPX["pin"], "version": "1.0.1"},
                }
            },
        )
    )

    failed = _claude(tmp_path, claude, bumped)
    assert len(failed.errors) == 2 and "x" not in claude.data
    again = _claude(tmp_path, claude, bumped)

    assert again.created == [f"{claude.path} mcpServers.x"], again
    assert claude.data["x"] == claude_entry(bumped["x"], CACHE)


def test_an_add_that_lands_in_another_file_is_an_error_not_owned(tmp_path: Path) -> None:
    claude = FakeClaude(tmp_path / ".claude.json", lands=False)

    result = _claude(tmp_path, claude, _servers(tmp_path))
    claude.lands = True
    again = _claude(tmp_path, claude, _servers(tmp_path))

    assert result.errors == [
        f"{claude.path} mcpServers.x: `claude mcp add-json` didn't write it to {claude.path}"
    ]
    assert result.created == [] and again.created == [f"{claude.path} mcpServers.x"]


def test_claude_uses_the_legacy_config_file_when_there_is_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from repo_template.mcp_globals import claude_config

    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert claude_config(tmp_path) == tmp_path / ".claude.json"
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/.config.json").write_text("{}")
    assert claude_config(tmp_path) == tmp_path / ".claude/.config.json"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "elsewhere"))
    assert claude_config(tmp_path) == tmp_path / "elsewhere/.claude.json"


def test_claude_servers_are_skipped_when_claude_reads_other_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deny rules go to ~/.claude/settings.json; Claude Code with CLAUDE_CONFIG_DIR set
    elsewhere wouldn't read them, so it gets no servers either."""
    from repo_template.standards import _sync_global_mcp

    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    claude = FakeClaude(tmp_path / "claude/.claude.json")
    result = Result(tmp_path)

    _sync_global_mcp(
        _agents(tmp_path / "catalog", {"x": NPX}), home.resolve(), result, check=False,
        stamp="s", claude=claude,
    )  # fmt: skip

    assert claude.calls == [] and any("CLAUDE_CONFIG_DIR is set" in n for n in result.notes)
    assert "x" in tomllib.loads((home / ".codex/config.toml").read_text())["mcp_servers"]


def test_an_unreadable_state_file_is_an_error_and_leaves_the_servers(tmp_path: Path) -> None:
    from repo_template.standards import _sync_global_mcp

    home = tmp_path / "home"
    (home / ".repo-template").mkdir(parents=True)
    (home / ".repo-template/globals-state.json").write_text("{nope")
    claude = FakeClaude(tmp_path / ".claude.json")
    result = Result(tmp_path)

    _sync_global_mcp(
        _agents(tmp_path / "catalog", {"x": NPX}), home, result, check=False, stamp="s",
        claude=claude,
    )  # fmt: skip

    assert len(result.errors) == 1 and "delete it to reset" in result.errors[0]
    assert claude.calls == []


def test_a_missing_config_file_is_a_fresh_start(tmp_path: Path) -> None:
    """Deleting ~/.claude.json or ~/.codex/config.toml resets them; it isn't removing servers."""
    claude = FakeClaude(tmp_path / ".claude.json")
    servers = _servers(tmp_path)
    _claude(tmp_path, claude, servers)
    claude.data, claude.present = {}, False
    assert _claude(tmp_path, claude, servers).created == [f"{claude.path} mcpServers.x"]

    path = _config(tmp_path)
    _codex(tmp_path, servers)
    path.unlink()
    assert _codex(tmp_path, servers).created == [f"{path} mcp_servers.x"]


def test_a_server_edited_by_hand_and_then_removed_stays_removed(tmp_path: Path) -> None:
    claude = FakeClaude(tmp_path / ".claude.json")
    servers = _servers(tmp_path)
    _claude(tmp_path, claude, servers)
    claude.data["x"] = {"type": "stdio", "command": "mine"}
    assert _claude(tmp_path, claude, servers).preserved  # kept, once
    del claude.data["x"]

    result = _claude(tmp_path, claude, servers)

    assert "x" not in claude.data and result.created == []


@pytest.mark.parametrize("emptied", ["catalog", "file"])
def test_the_last_codex_server_can_be_removed(tmp_path: Path, emptied: str) -> None:
    """With no other mcp_servers, removing ours leaves no empty table and no marker block."""
    from repo_template.standards import _sync_global_mcp

    path = _config(tmp_path, 'model = "o3"\n')
    servers = _servers(tmp_path)
    _codex(tmp_path, servers)
    result = Result(tmp_path)

    if emptied == "catalog":
        result = _codex(tmp_path, {})
    else:
        _sync_global_mcp(
            _agents(tmp_path / "empty", {}), tmp_path / "home", result, check=False, stamp="t",
            claude=None,
        )  # fmt: skip

    assert result.errors == [] and result.removed == [f"{path} mcp_servers.x"]
    assert path.read_text() == 'model = "o3"\n'


def test_codex_writes_through_a_symlinked_config(tmp_path: Path) -> None:
    dotfiles = tmp_path / "dotfiles/codex.toml"
    dotfiles.parent.mkdir()
    dotfiles.write_text('model = "o3"\n')
    path = tmp_path / "home/.codex/config.toml"
    path.parent.mkdir(parents=True)
    path.symlink_to(dotfiles)

    _codex(tmp_path, _servers(tmp_path))

    assert path.is_symlink() and "x" in tomllib.loads(dotfiles.read_text())["mcp_servers"]


def test_comments_after_the_block_and_before_foreign_tables_are_kept(tmp_path: Path) -> None:
    servers = _servers(tmp_path)
    path = _config(tmp_path)
    _codex(tmp_path, servers)
    text = path.read_text() + '\n# my notes\n\n# about this one\n[profiles.fast]\nmodel = "o3"\n'
    path.write_text(text)

    _codex(tmp_path, _servers(tmp_path / "b", deny=["other"]))

    after = path.read_text()
    assert "# my notes\n" in after and "# about this one\n[profiles.fast]" in after


def test_comments_after_the_block_at_the_end_of_the_file_are_kept(tmp_path: Path) -> None:
    path = _config(tmp_path)
    _codex(tmp_path, _servers(tmp_path))
    path.write_text(path.read_text() + "# keep me\n")

    _codex(tmp_path, _servers(tmp_path / "b", deny=["other"]))

    assert "# keep me\n" in path.read_text()


# Review findings for pack servers and the catalog.


def test_an_edited_entry_is_reported_once_then_kept_quietly(tmp_path: Path) -> None:
    root, catalog = _repository(tmp_path)
    _update(root, catalog, packs=["lc"])
    project = json.loads((root / ".mcp.json").read_text())
    project["mcpServers"]["docs"]["url"] = "https://mine.example.com/mcp"
    (root / ".mcp.json").write_text(json.dumps(project))

    first = _update(root, catalog)
    second = _update(root, catalog)

    assert first.preserved == [".mcp.json mcpServers.docs (edited in this repository; kept)"]
    assert second.preserved == [] and not _update(root, catalog, check=True).needs_attention
    assert read_manifest(root)["mcp_kept"] == {"docs": digest(project["mcpServers"]["docs"])}


def test_an_entry_deleted_in_the_repository_stays_deleted(tmp_path: Path) -> None:
    root, catalog = _repository(tmp_path)
    _update(root, catalog, packs=["lc"])
    (root / ".mcp.json").write_text(
        '{"mcpServers": {"team": {"type": "http", "url": "https://t"}}}'
    )

    first = _update(root, catalog)
    second = _update(root, catalog)

    assert first.preserved == [".mcp.json mcpServers.docs (deleted in this repository; kept)"]
    assert second.preserved == [] and "docs" not in json.loads((root / ".mcp.json").read_text())
    manifest = json.loads((root / ".repo-template.json").read_text())
    del manifest["mcp_kept"]  # how to have repo-template manage it again
    (root / ".repo-template.json").write_text(json.dumps(manifest))
    assert ".mcp.json mcpServers.docs" in _update(root, catalog).created


def test_adopting_a_repository_writes_its_codex_file_in_one_pass(tmp_path: Path) -> None:
    """The baseline .gitignore that ignores .codex/ is written in the same update."""
    _, catalog = _repository(tmp_path)
    root = tmp_path / "fresh"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "core.excludesFile", os.devnull], check=True)

    planned = _update(root, catalog, packs=["lc"], check=True)
    applied = _update(root, catalog, packs=["lc"])

    assert ".codex/config.toml (pack MCP servers)" in planned.created
    assert ".codex/config.toml (pack MCP servers)" in applied.created
    assert not _update(root, catalog, check=True).needs_attention


def test_a_failed_mcp_json_write_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from repo_template import mcp_project

    root, catalog = _repository(tmp_path)

    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(mcp_project, "write_file", fail)
    with pytest.raises(OSError, match="disk full"):
        _update(root, catalog, packs=["lc"])
    assert "mcp_servers" not in read_manifest(root)
    monkeypatch.undo()

    _update(root, catalog, packs=["lc"])
    assert not _update(root, catalog, check=True).needs_attention


def test_a_codex_folder_outside_the_repository_is_left_alone(tmp_path: Path) -> None:
    root, catalog = _repository(tmp_path)
    outside = tmp_path / "home/.codex"
    outside.mkdir(parents=True)
    (outside / "config.toml").write_text('model = "o3"\n')
    (root / ".codex").symlink_to(outside, target_is_directory=True)

    result = _update(root, catalog, packs=["lc"])

    assert ".codex (not a folder in this repository; left alone)" in result.preserved
    assert (outside / "config.toml").read_text() == 'model = "o3"\n'


def test_an_undefined_pack_freezes_its_servers(tmp_path: Path) -> None:
    """While a listed pack isn't defined (renamed, or not pulled yet), its servers' args can't
    be known: nothing is changed or removed, in either file."""
    root, catalog = _repository(tmp_path)
    _update(root, catalog, packs=["lc"])
    before = ((root / ".mcp.json").read_text(), (root / ".codex/config.toml").read_text())
    manifest = json.loads((root / ".repo-template.json").read_text())
    manifest["skill_packs"] = ["gone", "lc"]
    (root / ".repo-template.json").write_text(json.dumps(manifest))
    servers = json.loads((catalog / "mcp-servers.json").read_text())
    servers["servers"]["docs"]["url"] = "https://moved.example.com/mcp"
    (catalog / "mcp-servers.json").write_text(json.dumps(servers))

    result = _update(root, catalog)

    assert any("'gone'" in error for error in result.errors)
    assert ((root / ".mcp.json").read_text(), (root / ".codex/config.toml").read_text()) == before


AZ = {
    **NPX,
    "scope": "pack",
    "command": "uvx",
    "args": ["--from", "msmcp-azure==1", "azmcp", "server", "start", "--read-only"],
    "pin": {**NPX["pin"], "registry": "pypi", "package": "msmcp-azure", "version": "1"},
    "packArgs": ["--namespace"],
}


@pytest.mark.parametrize(
    ("ref", "message"),
    [
        ({"server": "az", "args": {"--namespace": ["${GITHUB_TOKEN}"]}}, "no placeholders"),
        ({"server": "az", "args": {"--namespace": ["hf_abcdefghijklmnop"]}}, "no secrets in args"),
        ({"server": "az", "args": {"--namespace": ["--dangerously-x"]}}, "never allowed"),
        ({"server": "az", "args": {"--read-only": ["false"]}}, "takes \\['--namespace'\\]"),
        ({"server": "az", "args": {"--mode": ["all"]}}, "takes \\['--namespace'\\]"),
        ({"server": "docs", "args": {"--header": ["x"]}}, "takes none from packs"),
        (
            {"server": "az", "args": {"--namespace": ["00000000-1111-2222-3333-444444444444"]}},
            "belong to each machine",
        ),
        ({"server": "az", "args": {"-x": ["y"]}}, "maps --flags"),
        ({"server": "az", "argz": {}}, "an MCP ref takes"),
    ],
)
def test_pack_args_are_only_the_flags_a_server_allows_and_checked_like_its_own(
    tmp_path: Path, ref: dict[str, Any], message: str
) -> None:
    agents = _agents(tmp_path, {"docs": URL, "az": AZ}, {"p": {"skills": [], "mcp": [ref]}})

    with pytest.raises(ValueError, match=message):
        pack_servers(agents, load_mcp_servers(agents))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"args": [*AZ["args"], "false"]}, "--read-only takes no value"),
        ({"args": [*AZ["args"][:-1], "--read-only=false"]}, "--read-only takes no value"),
        ({"args": [*AZ["args"], "--transport", "http"]}, "--transport is stdio only"),
        ({"args": [*AZ["args"], "--transport=http"]}, "--transport is stdio only"),
        ({"args": [*AZ["args"], "--dangerously-disable-ssrf-protections-by-namespace"]}, "never"),
        ({"args": [*AZ["args"], "--insecure-x"]}, "never allowed"),
        ({"args": [*AZ["args"], "--outgoing-auth-strategy", "x"]}, "never allowed"),
        ({"args": [*AZ["args"], "--subscription", "x"]}, "belong to each machine"),
        ({"env": {"AZURE_SUBSCRIPTION_ID": "x"}}, "belong to each machine"),
        ({"env": {"X": "00000000-1111-2222-3333-444444444444"}}, "belong to each machine"),
        ({"packArgs": ["--read-only"]}, "decides what the server may do"),
        ({"packArgs": ["--from"]}, "decides what the server may do"),
    ],
)
def test_the_catalog_refuses_what_would_widen_a_server(
    tmp_path: Path, change: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        load_mcp_servers(_agents(tmp_path, {"az": {**AZ, **change}}))


def test_a_transport_of_stdio_is_fine(tmp_path: Path) -> None:
    server = {**AZ, "args": [*AZ["args"], "--transport", "stdio"]}

    assert "stdio" in load_mcp_servers(_agents(tmp_path, {"az": server}))["az"].args


def test_a_young_pin_is_held_back_from_both_syncs(tmp_path: Path) -> None:
    """The catalog check reports it; the syncs don't install it meanwhile."""
    from datetime import UTC, datetime, timedelta

    from repo_template.mcp import usable

    recent = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    young = {**NPX, "pin": {**NPX["pin"], "publishedAt": recent}}
    servers = load_mcp_servers(_agents(tmp_path / "c", {"x": young, "docs": URL}))
    errors: list[str] = []

    kept = usable(servers, datetime.now(UTC), errors)

    assert list(kept) == ["docs"] and len(errors) == 1 and "not installed" in errors[0]
    root, catalog = _repository(tmp_path)
    catalog_servers = json.loads((catalog / "mcp-servers.json").read_text())
    catalog_servers["servers"]["docs"] = {**young, "scope": "pack"}
    (catalog / "mcp-servers.json").write_text(json.dumps(catalog_servers))
    result = _update(root, catalog, packs=["lc"])
    assert any("less than 7 days old" in error for error in result.errors)
    project = root / ".mcp.json"
    assert not project.exists() or "docs" not in json.loads(project.read_text())["mcpServers"]


def test_a_pack_with_an_unknown_key_is_refused(tmp_path: Path) -> None:
    agents = _agents(tmp_path, {"docs": URL}, {"p": {"skills": [], "mcp_servers": ["docs"]}})

    with pytest.raises(ValueError, match="unknown keys"):
        pack_servers(agents, load_mcp_servers(agents))


def test_the_cutoff_is_the_next_utc_midnight_whatever_the_offset(tmp_path: Path) -> None:
    pin = {**NPX["pin"], "publishedAt": "2026-09-01T20:00:00-05:00"}  # 01:00 UTC on the 2nd
    server = load_mcp_servers(_agents(tmp_path, {"x": {**NPX, "pin": pin}}))["x"]

    assert claude_entry(server, CACHE)["env"]["npm_config_before"] == "2026-09-03T00:00:00Z"


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"publishedAt": "2099-01-01T00:00:00Z"}, "publishedAt is in the future"),
        ({"publishedAt": "{recent}"}, "is less than 7 days old"),
        ({"publishedAt": "{recent}", "pinException": "fixes the crash on Node 20"}, None),
    ],
)
def test_the_catalog_check_holds_pins_to_the_cooldown(
    tmp_path: Path, change: dict[str, str], problem: str | None
) -> None:
    from datetime import UTC, datetime, timedelta

    from repo_template.catalog import _check_mcp, _Problems

    recent = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pin = {**NPX["pin"], **{k: v.replace("{recent}", recent) for k, v in change.items()}}
    root = tmp_path
    _agents(root, {"x": {**NPX, "pin": pin}})
    settings = {"portable": {"permissions": {"deny": ["mcp__*__run_unsafe"]}}, "defaults": {}}
    (root / ".agents/claude-settings.json").write_text(json.dumps(settings))
    problems = _Problems()

    _check_mcp(root, problems)

    found = [error for error in problems.errors if error.startswith("MCP server x")]
    assert len(found) == (problem is not None) and all(problem in error for error in found)


def test_the_catalog_check_wants_each_deny_in_the_portable_settings(tmp_path: Path) -> None:
    from repo_template.catalog import _check_mcp, _Problems

    _agents(tmp_path, {"x": NPX})
    (tmp_path / ".agents/claude-settings.json").write_text('{"portable": {}, "defaults": {}}')
    problems = _Problems()

    _check_mcp(tmp_path, problems)

    assert any(
        error.startswith("mcp__*__run_unsafe: an MCP server denies") for error in problems.errors
    )


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("AzureCliCredential", True),
        ("dev", True),
        ("hunter2", False),
        ("ClientSecretCredential", False),
    ],
)
def test_azure_token_credentials_only_names_a_credential_type(
    tmp_path: Path, value: str, ok: bool
) -> None:
    server = {**AZ, "env": {"AZURE_TOKEN_CREDENTIALS": value}}
    if ok:
        assert load_mcp_servers(_agents(tmp_path, {"az": server}))["az"].env
    else:
        with pytest.raises(ValueError, match="one of"):
            load_mcp_servers(_agents(tmp_path, {"az": server}))


def test_other_azure_secrets_stay_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="keyless"):
        load_mcp_servers(_agents(tmp_path, {"az": {**AZ, "env": {"AZURE_CLIENT_SECRET": "x"}}}))
