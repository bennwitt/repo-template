"""Packs-only adoption: a repository that takes only skill packs and their MCP servers."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from repo_template import cli
from repo_template.repository import update_repository
from repo_template.scaffold import new_project, update_project

DOCS = {"scope": "pack", "url": "https://docs.example.com/mcp", "source": "s", "why": "w"}


def _catalog(root: Path) -> Path:
    agents = root / ".agents"
    for name in ("ts-one", "ts-two"):
        (agents / "packs" / name).mkdir(parents=True)
        (agents / "packs" / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
    packs = {
        "ts": {"description": "TS", "skills": ["ts-one"], "mcp": ["docs"]},
        "more": {"description": "More", "skills": ["ts-two"]},
    }
    (agents / "skill-packs.json").write_text(json.dumps(packs))
    (agents / "mcp-servers.json").write_text(json.dumps({"schema": 1, "servers": {"docs": DOCS}}))
    return agents


def _web_app(root: Path) -> Path:
    """A JavaScript repository with its own .gitignore that ignores .claude/ and .agents/."""
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "core.excludesFile", os.devnull], check=True)
    (root / "package.json").write_text('{"name": "web"}\n')
    (root / ".gitignore").write_text("node_modules/\n.claude/\n.agents/\n.codex/\n")
    return root


def _files(root: Path) -> set[str]:
    """Every file and link outside .git, relative to root."""
    found: set[str] = set()
    for folder, dirs, files in os.walk(root):
        here = Path(folder).relative_to(root)
        dirs[:] = [name for name in dirs if (here / name).parts != (".git",)]
        found |= {str(here / name) for name in files}
        found |= {str(here / name) for name in dirs if (Path(folder) / name).is_symlink()}
    return found


def test_adopting_writes_only_the_manifest_links_and_pack_servers(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _web_app(tmp_path / "web")
    before = (root / ".gitignore").read_text()

    planned = update_repository(root, check=True, packs=["ts"], packs_only=True, agents_dir=agents)
    applied = update_repository(root, packs=["ts"], packs_only=True, agents_dir=agents)

    assert planned.created == applied.created
    assert _files(root) == {
        "package.json",
        ".gitignore",
        ".repo-template.json",
        ".mcp.json",
        ".claude/skills/ts-one",
        ".agents/skills/ts-one",
        ".codex/config.toml",
    }
    assert (root / ".gitignore").read_text() == before
    manifest = json.loads((root / ".repo-template.json").read_text())
    assert manifest["profile"] == "packs-only" and manifest["skill_packs"] == ["ts"]
    assert set(manifest) == {"schema", "template_version", "profile", "skill_packs", "mcp_servers"}
    assert list(manifest["mcp_servers"]) == ["docs"]
    hooks = subprocess.run(
        ["git", "-C", str(root), "config", "--get", "core.hooksPath"], capture_output=True
    )
    assert hooks.returncode == 1  # no hook path
    assert not update_repository(root, check=True, agents_dir=agents).needs_attention


def test_later_runs_follow_the_recorded_profile(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _web_app(tmp_path / "web")
    update_repository(root, packs=["ts"], packs_only=True, agents_dir=agents)

    added = update_repository(root, packs=["more"], agents_dir=agents)

    assert ".claude/skills/ts-two" in added.created
    assert not (root / "AGENTS.md").exists() and not (root / "pyproject.toml").exists()
    manifest_path = root / ".repo-template.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["skill_packs"] = ["more"]
    manifest_path.write_text(json.dumps(manifest))

    dropped = update_repository(root, agents_dir=agents)

    assert ".claude/skills/ts-one" in dropped.removed
    assert not (root / ".mcp.json").exists()  # only the dropped pack's server was in it
    assert "mcp_servers" not in json.loads(manifest_path.read_text())


def test_a_repository_on_the_baseline_isnt_adopted_packs_only(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = tmp_path / "service"
    new_project(root, name="service", description="S.", python_version="3.12")
    before = (root / ".repo-template.json").read_text()

    with pytest.raises(ValueError, match="has the python-uv baseline"):
        update_repository(root, packs=["ts"], packs_only=True, agents_dir=agents)
    assert (root / ".repo-template.json").read_text() == before


def test_adopting_needs_a_pack_and_a_packs_only_repository_gets_no_baseline(
    tmp_path: Path,
) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _web_app(tmp_path / "web")

    with pytest.raises(ValueError, match="name one with --pack"):
        update_repository(root, packs_only=True, agents_dir=agents)
    update_repository(root, packs=["more"], packs_only=True, agents_dir=agents)
    with pytest.raises(ValueError, match="takes only skill packs"):
        update_project(root)


def test_links_git_would_commit_are_reported_not_made(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _web_app(tmp_path / "web")
    (root / ".gitignore").write_text("node_modules/\n")

    result = update_repository(root, packs=["more"], packs_only=True, agents_dir=agents)

    assert result.preserved == [
        f"{folder}/ts-two (Git wouldn't ignore this link; ignore it so the skill can be linked)"
        for folder in (".claude/skills", ".agents/skills")
    ]
    assert not (root / ".claude").exists() and not (root / ".agents").exists()


def test_the_cli_adopts_then_checks_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _web_app(tmp_path / "web")
    real = cli.update_repository
    monkeypatch.setattr(
        cli, "update_repository", lambda *args, **kwargs: real(*args, agents_dir=agents, **kwargs)
    )

    assert cli.main(["update", str(root), "--packs-only", "--pack", "ts", "--no-input"]) == 0
    assert cli.main(["check", str(root)]) == 0
    assert "Standards are current." in capsys.readouterr().out
