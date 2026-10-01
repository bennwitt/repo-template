from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from repo_template.model import Result
from repo_template.policies import merge_marked_block
from repo_template.skillfile import set_field

GITIGNORE_START = "# >>> repo-template personal AI directories"
GITIGNORE_END = "# <<< repo-template personal AI directories"
GITIGNORE_CONTENT = "**/.agents/\n**/.claude/\n**/.codex/"


SKILL_MIRROR_TARGET = Path("../../.agents/skills")
SKILL_PACKS_NAME = "skill-packs.json"
SKILL_OVERRIDES_NAME = "skill-overrides.json"


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


def load_skill_packs(agents_dir: Path) -> dict[str, list[str]]:
    """Read <agents_dir>/skill-packs.json: {"pack": {"description": ..., "skills": [...]}}."""
    path = agents_dir / SKILL_PACKS_NAME
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    packs: dict[str, list[str]] = {}
    for name, definition in raw.items() if isinstance(raw, dict) else []:
        skills = definition.get("skills") if isinstance(definition, dict) else None
        if not isinstance(skills, list) or not all(isinstance(item, str) for item in skills):
            raise ValueError(f"{path}: pack {name!r} needs a list of skill names under 'skills'")
        packs[name] = skills
    return packs


def load_skill_overrides(agents_dir: Path) -> dict[str, dict[str, str | bool]]:
    """Read <agents_dir>/skill-overrides.json: {"skill": {"why": ..., "frontmatter": {...}}}."""
    path = agents_dir / SKILL_OVERRIDES_NAME
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    overrides: dict[str, dict[str, str | bool]] = {}
    for name, entry in raw.items() if isinstance(raw, dict) else []:
        fields = entry.get("frontmatter") if isinstance(entry, dict) else None
        if not isinstance(fields, dict) or not all(
            isinstance(value, str | bool) for value in fields.values()
        ):
            raise ValueError(
                f"{path}: {name!r} needs a 'frontmatter' object of strings or booleans"
            )
        overrides[name] = fields
    return overrides


def apply_skill_overrides(standards_root: Path, result: Result, *, check: bool) -> None:
    """Re-apply local frontmatter edits that `npx skills update` would otherwise overwrite."""
    agents = standards_root / ".agents"
    for name, fields in load_skill_overrides(agents).items():
        path = agents / "skills" / name / "SKILL.md"
        if not path.is_file():
            result.errors.append(f"{SKILL_OVERRIDES_NAME} overrides {name!r}, not in the catalog")
            continue
        text = path.read_text()
        updated = text
        for key, value in fields.items():
            updated = set_field(updated, key, value)
        if updated == text:
            result.unchanged.append(str(path))
            continue
        result.updated.append(f"{path} (override)")
        if not check:
            path.write_text(updated)


def _prune_links(
    directory: Path,
    owned: Callable[[Path], bool],
    keep: set[str],
    result: Result,
    *,
    check: bool,
    base: Path | None = None,
) -> None:
    """Remove links this tool owns whose skill is no longer wanted.

    Real directories, links this tool didn't create, and wanted skills are never touched.
    """
    if not directory.is_dir():
        return
    for entry in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
        if not entry.is_symlink() or entry.name in keep or not owned(entry):
            continue
        result.removed.append(str(entry.relative_to(base)) if base else str(entry))
        if not check:
            entry.unlink()


def _resolves_into(catalog: Path) -> Callable[[Path], bool]:
    resolved = catalog.resolve()
    return lambda entry: entry.resolve().parent == resolved


def _points_into(parent: Path) -> Callable[[Path], bool]:
    return lambda entry: Path(os.readlink(entry)).parent == parent


def _sync_links(
    directory: Path,
    targets: dict[str, Path],
    result: Result,
    *,
    check: bool,
    base: Path | None = None,
) -> None:
    """Make directory/<name> a symlink to targets[name] for every name."""
    for name, target in targets.items():
        link = directory / name
        label = str(link.relative_to(base)) if base else str(link)
        if link.is_symlink() and Path(os.readlink(link)) == target:
            result.unchanged.append(label)
            continue
        if link.exists() and not link.is_symlink():
            result.preserved.append(f"{label} (not a link; remove it so the skill can be linked)")
            continue
        (result.updated if link.is_symlink() else result.created).append(label)
        if check:
            continue
        directory.mkdir(parents=True, exist_ok=True)
        if link.is_symlink():
            link.unlink()
        link.symlink_to(target, target_is_directory=True)


def _sync_mirror(standards_root: Path, names: list[str], result: Result, *, check: bool) -> None:
    """Keep <standards>/.claude/skills/<name> as relative links to .agents/skills/<name>."""
    mirror = standards_root / ".claude/skills"
    _sync_links(mirror, {name: SKILL_MIRROR_TARGET / name for name in names}, result, check=check)
    _prune_links(mirror, _points_into(SKILL_MIRROR_TARGET), set(names), result, check=check)


def sync_project_packs(
    root: Path,
    packs: Sequence[str],
    result: Result,
    *,
    check: bool,
    agents_dir: Path,
) -> None:
    """Link each skill of the repository's packs into <root>/.claude/skills (ignored by Git).

    Links point at <agents_dir>/skills/<name>, normally ~/.agents/skills, so they follow the
    standards repository wherever it lives. Links for packs no longer listed are removed.
    """
    definitions = load_skill_packs(agents_dir)
    skills_dir = agents_dir / "skills"
    wanted: dict[str, Path] = {}
    for pack in packs:
        for name in definitions.get(pack, []):
            if (skills_dir / name / "SKILL.md").is_file():
                wanted[name] = skills_dir / name
            else:
                result.errors.append(f"skill pack {pack!r} lists {name!r}, which isn't installed")
    target_dir = root / ".claude/skills"
    _sync_links(target_dir, dict(sorted(wanted.items())), result, check=check, base=root)
    _prune_links(target_dir, _points_into(skills_dir), set(wanted), result, check=check, base=root)


def unknown_packs(packs: Sequence[str], agents_dir: Path) -> list[str]:
    known = load_skill_packs(agents_dir)
    return [pack for pack in packs if pack not in known]


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

    apply_skill_overrides(standards_root, result, check=check)
    skill_root = standards_root / ".agents/skills"
    names = skill_names(standards_root)
    packs = load_skill_packs(standards_root / ".agents")
    in_packs = {name for skills in packs.values() for name in skills}
    for missing in sorted(in_packs - set(names)):
        result.errors.append(f"{SKILL_PACKS_NAME} lists {missing!r}, which isn't in the catalog")
    global_names = [name for name in names if name not in in_packs]
    for name in global_names:
        _link(
            skill_root / name,
            home / ".claude/skills" / name,
            result,
            home=home,
            stamp=stamp,
            check=check,
        )
    _prune_links(
        home / ".claude/skills",
        _resolves_into(skill_root),
        set(global_names),
        result,
        check=check,
    )
    _sync_mirror(standards_root, global_names, result, check=check)

    _sync_global_gitignore(home, result, check=check)
    return result
