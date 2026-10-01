from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from repo_template.standards import find_standards_root, sync_globals


def _standards(tmp_path: Path) -> Path:
    root = tmp_path / "standards"
    skill = root / ".agents/skills/example"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Example\n")
    settings = root / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text('{"theme": "auto"}\n')
    return root


def test_global_sync_links_portable_files_and_keeps_claude_directory_local(
    tmp_path: Path,
) -> None:
    standards = _standards(tmp_path)
    home = tmp_path / "home"
    old_agents = home / ".agents"
    old_agents.mkdir(parents=True)
    (old_agents / "old.txt").write_text("old")
    old_settings = home / ".claude/settings.json"
    old_settings.parent.mkdir(parents=True)
    old_settings.write_text('{"old": true}\n')

    result = sync_globals(standards, home=home)

    assert result.updated
    assert (home / ".agents").is_symlink()
    assert (home / ".agents").resolve() == (standards / ".agents").resolve()
    assert (home / ".claude").is_dir()
    assert not (home / ".claude").is_symlink()
    assert (home / ".claude/settings.json").resolve() == (
        standards / ".claude/settings.json"
    ).resolve()
    assert (home / ".claude/skills/example").resolve() == (
        standards / ".agents/skills/example"
    ).resolve()
    assert "**/.agents/" in (home / ".config/git/ignore").read_text()
    backups = list((home / ".repo-template/backups").glob("*/.agents/old.txt"))
    assert len(backups) == 1

    check = sync_globals(standards, home=home, check=True)
    assert not check.needs_attention


def test_global_check_does_not_write(tmp_path: Path) -> None:
    standards = _standards(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    result = sync_globals(standards, home=home, check=True)

    assert result.created
    assert not (home / ".agents").exists()
    assert not (home / ".claude").exists()


def test_check_does_not_create_the_repository_mirror(tmp_path: Path) -> None:
    standards = _standards(tmp_path)

    result = sync_globals(standards, home=tmp_path / "home", check=True)

    assert str(standards / ".claude/skills/example") in result.created
    assert not (standards / ".claude/skills").exists()


def test_repository_mirror_uses_portable_relative_links(tmp_path: Path) -> None:
    standards = _standards(tmp_path)

    sync_globals(standards, home=tmp_path / "home")

    link = standards / ".claude/skills/example"
    assert os.readlink(link) == "../../.agents/skills/example"
    assert link.resolve() == (standards / ".agents/skills/example").resolve()


def test_links_to_a_deleted_skill_are_reported_then_pruned(tmp_path: Path) -> None:
    standards = _standards(tmp_path)
    home = tmp_path / "home"
    sync_globals(standards, home=home)
    shutil.rmtree(standards / ".agents/skills/example")

    planned = sync_globals(standards, home=home, check=True)

    assert planned.removed == [
        str(home / ".claude/skills/example"),
        str(standards / ".claude/skills/example"),
    ]
    assert (home / ".claude/skills/example").is_symlink()

    sync_globals(standards, home=home)

    assert not (home / ".claude/skills/example").is_symlink()
    assert not (standards / ".claude/skills/example").is_symlink()
    assert not sync_globals(standards, home=home, check=True).needs_attention


def test_pruning_leaves_entries_the_catalog_does_not_own(tmp_path: Path) -> None:
    standards = _standards(tmp_path)
    home = tmp_path / "home"
    sync_globals(standards, home=home)
    skills = home / ".claude/skills"
    (skills / "synced").mkdir()
    other = tmp_path / "other/skill"
    other.mkdir(parents=True)
    (skills / "elsewhere").symlink_to(other, target_is_directory=True)
    (skills / "gone-elsewhere").symlink_to(tmp_path / "other/missing", target_is_directory=True)
    (skills / "npx-style").symlink_to(Path("../../.agents/skills/npx-style"))

    result = sync_globals(standards, home=home)

    assert result.removed == [str(skills / "npx-style")]
    assert (skills / "synced").is_dir()
    assert (skills / "elsewhere").is_symlink()
    assert (skills / "gone-elsewhere").is_symlink()


def test_a_named_standards_root_must_be_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    standards = _standards(tmp_path)
    monkeypatch.setenv("AI_DEV_STANDARDS", str(standards))

    with pytest.raises(ValueError, match="--standards-root"):
        find_standards_root(tmp_path / "missing")
    assert find_standards_root() == standards.resolve()

    monkeypatch.setenv("AI_DEV_STANDARDS", str(tmp_path / "missing"))
    with pytest.raises(ValueError, match="AI_DEV_STANDARDS"):
        find_standards_root()
