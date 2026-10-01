from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from repo_template.repository import create_repository, update_repository
from repo_template.scaffold import new_project, skill_packs
from repo_template.standards import sync_globals


def _catalog(root: Path) -> Path:
    """A standards repository whose .agents holds two pack skills and one global skill."""
    agents = root / ".agents"
    for name in ("core", "lc-one", "lc-two"):
        skill = agents / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n")
    (agents / "skill-packs.json").write_text(
        json.dumps({"lc": {"description": "LangChain", "skills": ["lc-one", "lc-two"]}})
    )
    (root / ".claude").mkdir()
    (root / ".claude/settings.json").write_text("{}\n")
    return agents


def _repository(root: Path) -> Path:
    new_project(root, name=root.name, description="Sample.", python_version="3.12")
    return root


def test_globals_links_only_skills_outside_packs(tmp_path: Path) -> None:
    standards = tmp_path / "standards"
    _catalog(standards)
    home = tmp_path / "home"
    (home / ".claude/skills").mkdir(parents=True)
    (home / ".claude/skills/lc-one").symlink_to(standards / ".agents/skills/lc-one")

    result = sync_globals(standards, home=home)

    assert sorted(os.listdir(home / ".claude/skills")) == ["core"]
    assert sorted(os.listdir(standards / ".claude/skills")) == ["core"]
    assert str(home / ".claude/skills/lc-one") in result.removed


def test_globals_reports_a_pack_listing_a_missing_skill(tmp_path: Path) -> None:
    standards = tmp_path / "standards"
    agents = _catalog(standards)
    (agents / "skill-packs.json").write_text(json.dumps({"lc": {"skills": ["lc-one", "gone"]}}))

    result = sync_globals(standards, home=tmp_path / "home", check=True)

    assert any("'gone'" in error for error in result.errors)


def test_update_with_a_pack_links_it_and_records_it(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")

    planned = update_repository(
        root, check=True, hooks=False, lock=False, packs=["lc"], agents_dir=agents
    )
    applied = update_repository(root, hooks=False, lock=False, packs=["lc"], agents_dir=agents)

    expected = [".claude/skills/lc-one", ".claude/skills/lc-two"]
    assert planned.created == expected
    assert applied.created == expected
    assert os.readlink(root / ".claude/skills/lc-one") == str(agents / "skills/lc-one")
    assert skill_packs(root) == ["lc"]
    current = update_repository(root, check=True, hooks=False, lock=False, agents_dir=agents)
    assert not current.needs_attention


def test_dropping_a_pack_removes_only_its_links(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    update_repository(root, hooks=False, lock=False, packs=["lc"], agents_dir=agents)
    own_skill = root / ".claude/skills/project-only"
    own_skill.mkdir()
    manifest_path = root / ".repo-template.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["skill_packs"]
    manifest_path.write_text(json.dumps(manifest))

    result = update_repository(root, hooks=False, lock=False, agents_dir=agents)

    assert result.removed == [".claude/skills/lc-one", ".claude/skills/lc-two"]
    assert sorted(os.listdir(root / ".claude/skills")) == ["project-only"]


def test_unknown_pack_is_rejected_before_anything_changes(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    before = (root / ".repo-template.json").read_text()

    with pytest.raises(ValueError, match="unknown skill pack: nope"):
        update_repository(root, hooks=False, lock=False, packs=["nope"], agents_dir=agents)
    assert (root / ".repo-template.json").read_text() == before


def test_update_never_touches_a_standards_repository_mirror(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    mirror = root / ".claude/skills"
    mirror.mkdir(parents=True)
    (mirror / "core").symlink_to(Path("../../.agents/skills/core"))

    result = update_repository(root, hooks=False, lock=False, agents_dir=agents)

    assert result.removed == []
    assert (mirror / "core").is_symlink()


def test_new_repository_can_start_with_a_pack(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")

    result = create_repository(
        tmp_path / "agent",
        name="agent",
        description="Agent.",
        python_version="3.12",
        git=False,
        lock=False,
        packs=["lc"],
        agents_dir=agents,
    )

    assert ".claude/skills/lc-one" in result.created
    assert skill_packs(result.root) == ["lc"]
