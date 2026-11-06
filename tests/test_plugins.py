import json
from pathlib import Path

import pytest

from repo_template.plugins import reconcile, state_path, supplied, tree_digest


@pytest.mark.parametrize("client", ["codex", "claude"])
def test_native_selection_is_verified_before_suppressing_duplicates(tmp_path: Path, client: str):
    agents, home = tmp_path / "agents", tmp_path / "home"
    agents.mkdir()
    (agents / "skill-sources.json").write_text(
        json.dumps(
            {
                "plugins": {
                    "sample@official": {
                        "source": "owner/official",
                        "clients": ["claude", "codex"],
                        "skills": ["skill"],
                        "mcp": ["docs"],
                    }
                }
            }
        )
    )
    install = home / f".{client}/plugins/cache/official/sample/1.0"
    marketplace = tmp_path / "marketplace"
    (marketplace / ".claude-plugin").mkdir(parents=True)
    (marketplace / ".claude-plugin/marketplace.json").write_text(
        json.dumps({"plugins": [{"name": "sample", "source": "./reviewed"}]})
    )
    reviewed = marketplace / "reviewed"
    (reviewed / "skills/skill").mkdir(parents=True)
    (reviewed / "plugin.json").write_text('{"name":"sample"}')
    (reviewed / "skills/skill/SKILL.md").write_text("skill")
    catalog_path = agents / "skill-sources.json"
    catalog = json.loads(catalog_path.read_text())
    catalog["plugins"]["sample@official"].update(
        reviewedRevision="a" * 40, reviewedDigest=tree_digest(reviewed)
    )
    catalog_path.write_text(json.dumps(catalog))
    calls = []

    def run(argv):
        calls.append(list(argv))
        if argv[0] == "git":
            return "a" * 40
        if argv[2:4] == ["marketplace", "list"]:
            return [
                {"name": "official", "source": {"repo": "owner/official"}, "root": str(marketplace)}
            ]
        if argv[2] == "list":
            row = {
                "id": "sample@official",
                "pluginId": "sample@official",
                "version": "1.0",
                "enabled": True,
                "installed": True,
                "installPath": str(install),
            }
            return [row] if install.exists() else []
        if argv[2] in {"add", "install"}:
            install.mkdir(parents=True)
            (install / "plugin.json").write_text('{"name":"sample"}')
            (install / "skills/skill").mkdir(parents=True)
            (install / "skills/skill/SKILL.md").write_text("skill")

    selected = f"{client}:sample@official"
    preview = reconcile(agents, home, [selected], [], check=True, run=run)
    assert preview.notes and not calls and not state_path(home).exists()
    assert supplied(agents, home, client, "skills") == set()
    result = reconcile(agents, home, [selected], [], check=False, run=run)
    assert not result.errors
    assert supplied(agents, home, client, "skills") == {"skill"}

    def fail_uninstall(argv):
        raise ValueError("native uninstall failed")

    failed = reconcile(
        agents, home, [], [], check=False, revoke_write=[selected], run=fail_uninstall
    )
    assert any("NOT revoked" in error for error in failed.errors)
    assert selected in json.loads(state_path(home).read_text())["write_mcp"]
    assert not failed.removed and install.exists()
    (install / "plugin.json").write_text('{"changed":true}')
    assert supplied(agents, home, client, "skills") == set()
    calls.clear()
    removed = reconcile(agents, home, [], [selected], check=False, run=run)
    assert removed.preserved and not calls and install.exists()
    revoked = reconcile(agents, home, [], [], check=False, revoke_write=[selected], run=run)
    assert revoked.errors and "NOT revoked" in revoked.errors[0]
    assert selected in json.loads(state_path(home).read_text())["write_mcp"]


@pytest.mark.parametrize("client", ["codex", "claude"])
def test_batch_receipts_missing_assets_wrong_origins_and_removal(tmp_path, client):
    agents, home = tmp_path / "agents", tmp_path / "home"
    agents.mkdir()
    catalog = {
        "plugins": {
            f"{n}@official": {
                "source": "owner/official",
                "clients": [client],
                "skills": [n, "missing"],
            }
            for n in ["one", "two"]
        }
    }
    (agents / "skill-sources.json").write_text(json.dumps(catalog))
    paths = {}
    for name in ["one", "two"]:
        path = home / f".{client}/plugins/cache/official/{name}/1.0"
        (path / f"skills/{name}").mkdir(parents=True)
        (path / f"skills/{name}/SKILL.md").write_text(name)
        (path / "plugin.json").write_text(json.dumps({"name": name}))
        paths[name] = path
    calls = []
    origin = "unrelated/source"

    def run(argv):
        calls.append(argv)
        if argv[2:4] == ["marketplace", "list"]:
            return [{"name": "official", "source": {"repo": origin}}]
        if argv[2] == "list":
            return [
                {"id": f"{n}@official", "version": "1.0", "enabled": True, "installPath": str(p)}
                for n, p in paths.items()
            ]
        if argv[2] in {"remove", "uninstall"}:
            paths.pop(argv[3].split("@")[0])

    selectors = [f"{client}:{n}@official" for n in paths]
    rejected = reconcile(agents, home, selectors, [], check=False, run=run)
    assert rejected.errors and not supplied(agents, home, client, "skills")
    origin = "owner/official"
    result = reconcile(agents, home, selectors, [], check=False, run=run)
    assert not result.errors and result.notes
    assert supplied(agents, home, client, "skills") == {"one", "two"}
    result = reconcile(agents, home, [], selectors, check=False, run=run)
    assert not result.errors and not supplied(agents, home, client, "skills")
    assert not paths


def test_failed_plugin_install_keeps_fallback_and_writes_need_explicit_activation(tmp_path: Path):
    agents, home = tmp_path / "agents", tmp_path / "home"
    agents.mkdir()
    (agents / "skill-sources.json").write_text(
        json.dumps(
            {
                "plugins": {
                    "cloud@official": {
                        "source": "owner/official",
                        "clients": ["codex"],
                        "writeCapable": True,
                    }
                }
            }
        )
    )
    with pytest.raises(ValueError, match="allow-write-mcp"):
        reconcile(agents, home, ["codex:cloud@official"], [], check=False)
    result = reconcile(
        agents,
        home,
        ["codex:cloud@official"],
        [],
        check=False,
        allow_write=["codex:cloud@official"],
        run=lambda _: [],
    )
    assert result.errors and not json.loads(state_path(home).read_text())["plugins"]
    assert not json.loads(state_path(home).read_text())["write_mcp"]


def test_unowned_plugin_removal_is_preserved(tmp_path: Path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "skill-sources.json").write_text(
        json.dumps(
            {"plugins": {"sample@official": {"source": "owner/official", "clients": ["codex"]}}}
        )
    )
    calls = []
    result = reconcile(
        agents,
        tmp_path / "home",
        [],
        ["codex:sample@official"],
        check=False,
        run=lambda args: calls.append(args),
    )
    assert result.preserved and not calls


def test_plugin_digest_includes_executable_permissions(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text("same bytes")
    before = tree_digest(tmp_path)
    path.chmod(path.stat().st_mode | 0o111)
    assert tree_digest(tmp_path) != before


def test_disabled_existing_plugin_is_never_installed_or_rolled_back(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "skill-sources.json").write_text(
        json.dumps(
            {"plugins": {"sample@official": {"source": "owner/official", "clients": ["codex"]}}}
        )
    )
    calls = []

    def run(argv):
        calls.append(argv)
        if argv[2:4] == ["marketplace", "list"]:
            return []
        return [{"id": "sample@official", "installed": True, "enabled": False}]

    result = reconcile(
        agents, tmp_path / "home", ["codex:sample@official"], [], check=False, run=run
    )
    assert result.errors and "existing plugin" in result.errors[0]
    assert all("list" in call for call in calls)


def test_optional_mcp_needs_explicit_machine_grant_without_credentials(tmp_path, monkeypatch):
    from repo_template.maintenance import atomic_json
    from repo_template.mcp import load_mcp_servers
    from repo_template.plugins import filter_servers

    agents = Path(__file__).resolve().parents[1] / ".agents"
    servers = load_mcp_servers(agents)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    normal = filter_servers(agents, tmp_path, servers)
    assert "langsmith" not in normal and "azure-write" not in normal
    atomic_json(state_path(tmp_path), {"plugins": {}, "write_mcp": ["langsmith"]})
    allowed = filter_servers(agents, tmp_path, servers)
    assert "langsmith" in allowed and "azure-write" not in allowed
    atomic_json(state_path(tmp_path), {"plugins": {}, "write_mcp": []})
    assert "langsmith" not in filter_servers(agents, tmp_path, servers)


def test_failed_post_install_admission_removes_new_plugin_and_keeps_diagnostics(
    tmp_path, monkeypatch
):
    import shutil

    from repo_template import plugins

    agents, home = tmp_path / "agents", tmp_path / "home"
    agents.mkdir()
    (agents / "skill-sources.json").write_text(
        json.dumps(
            {
                "plugins": {
                    "sample@official": {
                        "source": "owner/official",
                        "clients": ["codex"],
                        "reviewedRevision": "a" * 40,
                        "reviewedDigest": "b" * 64,
                    }
                }
            }
        )
    )
    install = home / ".codex/plugins/cache/official/sample/1.0"
    calls = []

    def run(argv):
        calls.append(argv)
        if argv[2:4] == ["marketplace", "list"]:
            return [{"name": "official", "source": {"repo": "owner/official"}}]
        if argv[2] == "list":
            return (
                [
                    {
                        "id": "sample@official",
                        "version": "1.0",
                        "enabled": True,
                        "installPath": str(install),
                    }
                ]
                if install.exists()
                else []
            )
        if argv[2] == "add":
            install.mkdir(parents=True)
            (install / "plugin.json").write_text('{"name":"sample"}')
        if argv[2] == "remove":
            shutil.rmtree(install)

    monkeypatch.setattr(plugins, "_reviewed_candidate", lambda *a: None)
    result = reconcile(agents, home, ["codex:sample@official"], [], check=False, run=run)
    assert result.errors and not install.exists()
    assert list((home / ".repo-template/backups").glob("plugin-*/content/plugin.json"))
    assert not supplied(agents, home, "codex", "skills")
