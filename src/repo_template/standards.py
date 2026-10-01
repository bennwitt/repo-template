from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from repo_template.model import Result
from repo_template.policies import merge_marked_block

GITIGNORE_START = "# >>> repo-template personal AI directories"
GITIGNORE_END = "# <<< repo-template personal AI directories"
GITIGNORE_CONTENT = "**/.agents/\n**/.claude/\n**/.codex/"


SKILL_MIRROR_TARGET = Path("../../.agents/skills")


def _is_standards_root(path: Path) -> bool:
    return (path / ".agents/skills").is_dir() and (path / ".claude/settings.json").is_file()


def find_standards_root(explicit: Path | None = None) -> Path:
    """Use --standards-root, else $AI_DEV_STANDARDS, else search; a named root must be valid."""
    named = [(explicit, "--standards-root")] if explicit is not None else []
    env_root = os.environ.get("AI_DEV_STANDARDS")
    if not named and env_root:
        named = [(Path(env_root), "AI_DEV_STANDARDS")]
    for candidate, source in named:
        root = candidate.expanduser().resolve()
        if not _is_standards_root(root):
            raise ValueError(
                f"{source} {root} is not a standards repository "
                "(it needs .agents/skills/ and .claude/settings.json)"
            )
        return root
    for candidate in [Path.cwd(), *Path(__file__).resolve().parents]:
        root = candidate.expanduser().resolve()
        if _is_standards_root(root):
            return root
    raise ValueError("standards root not found; pass --standards-root or set AI_DEV_STANDARDS")


def skill_names(standards_root: Path) -> list[str]:
    """Every catalog skill: a folder under .agents/skills/ that contains a SKILL.md."""
    skill_root = standards_root / ".agents/skills"
    return sorted(
        (
            skill.name
            for skill in skill_root.iterdir()
            if skill.name != "synced" and (skill / "SKILL.md").is_file()
        ),
        key=str.casefold,
    )


def _prune_stale_links(
    directory: Path, catalog: Path, keep: set[str], result: Result, *, check: bool
) -> None:
    """Remove links that point into the catalog at a skill that no longer exists.

    Real directories, links to anywhere else, and live skills are never touched.
    """
    if not directory.is_dir():
        return
    catalog = catalog.resolve()
    for entry in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
        if not entry.is_symlink() or entry.name in keep:
            continue
        target = entry.resolve()
        if target.parent != catalog or (target / "SKILL.md").is_file():
            continue
        result.removed.append(str(entry))
        if not check:
            entry.unlink()


def _sync_mirror(standards_root: Path, names: list[str], result: Result, *, check: bool) -> None:
    """Keep <standards>/.claude/skills/<name> as relative links to .agents/skills/<name>."""
    mirror = standards_root / ".claude/skills"
    for name in names:
        link = mirror / name
        expected = SKILL_MIRROR_TARGET / name
        if link.is_symlink() and Path(os.readlink(link)) == expected:
            result.unchanged.append(str(link))
            continue
        if link.exists() and not link.is_symlink():
            result.preserved.append(f"{link} (not a link; remove it so the mirror can link it)")
            continue
        (result.updated if link.is_symlink() else result.created).append(str(link))
        if check:
            continue
        mirror.mkdir(parents=True, exist_ok=True)
        if link.is_symlink():
            link.unlink()
        link.symlink_to(expected, target_is_directory=True)
    _prune_stale_links(mirror, standards_root / ".agents/skills", set(names), result, check=check)


def _same_link(destination: Path, source: Path) -> bool:
    if not destination.is_symlink():
        return False
    try:
        return destination.resolve() == source.resolve()
    except OSError:
        return False


def _backup_path(home: Path, destination: Path, stamp: str) -> Path:
    relative = destination.relative_to(home)
    return home / ".repo-template" / "backups" / stamp / relative


def _link(
    source: Path,
    destination: Path,
    result: Result,
    *,
    home: Path,
    stamp: str,
    check: bool,
) -> None:
    label = str(destination)
    if _same_link(destination, source):
        result.unchanged.append(label)
        return
    exists = destination.exists() or destination.is_symlink()
    (result.updated if exists else result.created).append(label)
    if check:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if exists:
        backup = _backup_path(home, destination, stamp)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(destination), str(backup))
    destination.symlink_to(source, target_is_directory=source.is_dir())


def _merge_global_gitignore(existing: str) -> str:
    return merge_marked_block(existing, GITIGNORE_CONTENT, GITIGNORE_START, GITIGNORE_END)


def _sync_global_gitignore(home: Path, result: Result, *, check: bool) -> None:
    path = home / ".config/git/ignore"
    existing = path.read_text() if path.exists() else ""
    proposed = _merge_global_gitignore(existing)
    if proposed == existing:
        result.unchanged.append(str(path))
        return
    (result.updated if path.exists() else result.created).append(str(path))
    if not check:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(proposed)


def sync_globals(
    standards_root: Path,
    *,
    home: Path | None = None,
    check: bool = False,
) -> Result:
    standards_root = find_standards_root(standards_root)
    home = (home or Path.home()).expanduser().resolve()
    result = Result(standards_root)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")

    agents = standards_root / ".agents"
    claude_settings = standards_root / ".claude/settings.json"
    _link(agents, home / ".agents", result, home=home, stamp=stamp, check=check)
    _link(
        claude_settings,
        home / ".claude/settings.json",
        result,
        home=home,
        stamp=stamp,
        check=check,
    )

    skill_root = standards_root / ".agents/skills"
    names = skill_names(standards_root)
    for name in names:
        _link(
            skill_root / name,
            home / ".claude/skills" / name,
            result,
            home=home,
            stamp=stamp,
            check=check,
        )
    _prune_stale_links(home / ".claude/skills", skill_root, set(names), result, check=check)
    _sync_mirror(standards_root, names, result, check=check)

    _sync_global_gitignore(home, result, check=check)
    return result
