from __future__ import annotations

from pathlib import Path

from repo_template.standards import sync_globals


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
