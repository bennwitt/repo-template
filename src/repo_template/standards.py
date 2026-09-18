from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from repo_template.model import Result

GITIGNORE_START = "# >>> repo-template personal AI directories"
GITIGNORE_END = "# <<< repo-template personal AI directories"
GITIGNORE_CONTENT = "**/.agents/\n**/.claude/\n**/.codex/"


def find_standards_root(explicit: Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    env_root = os.environ.get("AI_DEV_STANDARDS")
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend([Path.cwd(), *Path(__file__).resolve().parents])
    for candidate in candidates:
        root = candidate.expanduser().resolve()
        if (root / ".agents/skills").is_dir() and (root / ".claude/settings.json").is_file():
            return root
    raise ValueError("standards root not found; pass --standards-root or set AI_DEV_STANDARDS")


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
    block = f"{GITIGNORE_START}\n{GITIGNORE_CONTENT}\n{GITIGNORE_END}\n"
    start = existing.find(GITIGNORE_START)
    end = existing.find(GITIGNORE_END)
    if start >= 0 and end >= start:
        end += len(GITIGNORE_END)
        if end < len(existing) and existing[end] == "\n":
            end += 1
        return existing[:start] + block + existing[end:]
    prefix = existing.rstrip()
    return f"{prefix}\n\n{block}" if prefix else block


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
    for skill in sorted(skill_root.iterdir(), key=lambda item: item.name.casefold()):
        if skill.name == "synced" or not (skill / "SKILL.md").is_file():
            continue
        _link(
            skill,
            home / ".claude/skills" / skill.name,
            result,
            home=home,
            stamp=stamp,
            check=check,
        )

    _sync_global_gitignore(home, result, check=check)
    return result
