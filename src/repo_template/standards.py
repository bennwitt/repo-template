from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from repo_template.catalog import (
    LICENSES_DIR,
    LOCK_NAME,
    NOTICES_NAME,
    PACKS_DIR,
    SHA,
    SKILLS_DIR,
    SOURCES_NAME,
    blob_sha,
    integrity,
    lock_completion,
    origin,
    override,
    placement,
    read_skill,
    skill_folder,
    sync_documents,
)
from repo_template.mcp import load_mcp_servers, usable
from repo_template.mcp_globals import (
    ClaudeCli,
    ClaudeMcp,
    claude_config_elsewhere,
    codex_config,
    sync_claude_mcp,
    sync_codex_mcp,
)
from repo_template.model import Result
from repo_template.policies import marked_block_intact, merge_marked_block
from repo_template.settings import SOURCE_NAME, sync_claude_settings
from repo_template.skillfile import field_lines

GITIGNORE_START = "# >>> repo-template personal AI directories"
GITIGNORE_END = "# <<< repo-template personal AI directories"
GITIGNORE_CONTENT = "**/.agents/\n**/.claude/\n**/.codex/\n**/.playwright-cli/\n**/.playwright-mcp/"


SKILL_MIRROR_TARGET = Path("../../.agents/skills")
SKILL_PACKS_NAME = "skill-packs.json"
SKILL_OVERRIDES_NAME = "skill-overrides.json"
FIELD_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
Paths = Callable[[list[Path]], set[Path]]


def _is_standards_root(path: Path) -> bool:
    return (path / ".agents/skills").is_dir() and (path / ".agents" / SOURCE_NAME).is_file()


def _is_full_catalog(path: Path) -> bool:
    """A catalog with provenance (this repository), not a minimal standards root: then the
    lock and the sources are required, so deleting them can't turn the checks off."""
    markers = (LOCK_NAME, SOURCES_NAME, LICENSES_DIR, NOTICES_NAME)
    if any((path / marker).exists() for marker in markers):
        return True
    try:
        metadata = tomllib.loads((path / "pyproject.toml").read_text()).get("project", {})
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return isinstance(metadata, dict) and metadata.get("name") == "repo-template"


def _is_this_project(path: Path) -> bool:
    """A standards root that is a checkout of repo-template itself, not just any repository with
    .agents/skills (which `npx skills add` creates) and a settings file."""
    if not (_is_standards_root(path) and (path / ".agents/.skill-lock.json").is_file()):
        return False
    try:
        metadata = tomllib.loads((path / "pyproject.toml").read_text()).get("project", {})
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return isinstance(metadata, dict) and metadata.get("name") == "repo-template"


def _installed_root() -> Path | None:
    """The standards repository this package runs from (an editable install), if any."""
    for parent in Path(__file__).resolve().parents:
        if _is_this_project(parent):
            return parent
    return None


def installed_root() -> Path | None:
    """The standards repository this CLI runs from, when it is an editable install of one."""
    return _installed_root()


def find_standards_root(explicit: Path | None = None) -> Path:
    """Use --standards-root, else $AI_DEV_STANDARDS, else the checkout this CLI is installed
    from, else the current directory if it is a repo-template checkout.

    A named root must be valid. Two different checkouts (the installed one and the current
    directory) are ambiguous, so the root must then be named.
    """
    named = [(explicit, "--standards-root")] if explicit is not None else []
    env_root = os.environ.get("AI_DEV_STANDARDS")
    if not named and env_root:
        named = [(Path(env_root), "AI_DEV_STANDARDS")]
    for candidate, source in named:
        root = candidate.expanduser().resolve()
        if not _is_standards_root(root):
            raise ValueError(
                f"{source} {root} is not a standards repository "
                f"(it needs .agents/skills/ and .agents/{SOURCE_NAME})"
            )
        return root
    installed = _installed_root()
    here = next(
        (path for path in [Path.cwd(), *Path.cwd().parents] if _is_this_project(path)), None
    )
    if installed and here and installed != here.resolve():
        raise ValueError(
            f"two standards repositories: this CLI runs from {installed}, but the current "
            f"directory is in {here}; pass --standards-root to choose one"
        )
    found = installed or (here.resolve() if here else None)
    if found is None:
        raise ValueError("standards root not found; pass --standards-root or set AI_DEV_STANDARDS")
    return found


def skill_names(standards_root: Path) -> list[str]:
    """Every catalog skill: a folder holding a SKILL.md under .agents/skills/ (global skills)
    or .agents/packs/ (pack skills)."""
    names: set[str] = set()
    for folder in (standards_root / SKILLS_DIR, standards_root / PACKS_DIR):
        if folder.is_dir():
            names.update(
                skill.name
                for skill in folder.iterdir()
                if skill.name != "synced" and (skill / "SKILL.md").is_file()
            )
    return sorted(names, key=str.casefold)


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
        for key, value in fields.items():
            if not FIELD_NAME.fullmatch(key) or (isinstance(value, str) and "---" in value):
                # Claude Code ends the frontmatter at the first "---", even inside a value
                raise ValueError(f"{path}: {name!r} can't set {key!r} to a value with '---'")
        upstream, base = entry.get("upstream"), entry.get("base")
        if upstream is not None and not (isinstance(upstream, str) and SHA.fullmatch(upstream)):
            raise ValueError(f"{path}: {name!r} 'upstream' must be a 40-character blob SHA")
        if base is not None and not (
            isinstance(base, dict) and all(isinstance(raw, str | None) for raw in base.values())
        ):
            raise ValueError(f"{path}: {name!r} 'base' must map fields to their upstream text")
        overrides[name] = fields
    return overrides


def _write_exact(path: Path, text: str) -> None:
    """Write atomically, keeping the text's own line endings."""
    temporary = path.with_name(f".{path.name}.repo-template-tmp")
    with temporary.open("w", newline="") as handle:
        handle.write(text)
    temporary.replace(path)


def apply_skill_overrides(standards_root: Path, result: Result, *, check: bool) -> set[str]:
    """Re-apply local frontmatter edits that vendoring a skill again would overwrite, mark each
    changed SKILL.md, and record in each override the upstream text it replaces. Returns the
    skills whose SKILL.md it rewrote (or, with check, would)."""
    agents = standards_root / ".agents"
    overrides = load_skill_overrides(agents)
    rewritten: set[str] = set()
    if not overrides:
        return rewritten
    records_path = agents / SKILL_OVERRIDES_NAME
    records = json.loads(records_path.read_text())
    completes = lock_completion(standards_root)
    recorded = False
    for name, fields in overrides.items():
        path = skill_folder(standards_root, name) / "SKILL.md"
        if not path.is_file():
            result.errors.append(f"{SKILL_OVERRIDES_NAME} overrides {name!r}, not in the catalog")
            continue
        text = read_skill(path)
        try:
            upstream, updated = override(
                text, fields, records[name], completes(name, text), origin(standards_root, name)
            )
        except ValueError as exc:
            result.errors.append(f"{SKILL_OVERRIDES_NAME} can't override {name!r}: {exc}")
            continue
        provenance = {
            "upstream": blob_sha(upstream.encode()),
            "base": {key: field_lines(upstream, key) for key in fields},
        }
        if any(records[name].get(key) != value for key, value in provenance.items()):
            records[name].update(provenance)
            recorded = True
        if updated == text:
            result.unchanged.append(str(path))
            continue
        result.updated.append(f"{path} (override)")
        rewritten.add(name)
        if not check:
            _write_exact(path, updated)
    if recorded:
        result.updated.append(f"{records_path} (the upstream text each override replaces)")
        if not check:
            _write_exact(records_path, json.dumps(records, indent=2, ensure_ascii=False) + "\n")
    return rewritten


def _prune_links(
    directory: Path,
    owned: Callable[[Path], bool],
    keep: set[str],
    result: Result,
    *,
    check: bool,
    base: Path | None = None,
    tracked: Callable[[Path], bool] | None = None,
) -> None:
    """Remove links this tool owns whose skill is no longer wanted.

    Real directories, links this tool didn't create, links the repository tracks, and wanted
    skills are never touched.
    """
    if not directory.is_dir():
        return
    for entry in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
        if not entry.is_symlink() or entry.name in keep or not owned(entry):
            continue
        if tracked is not None and tracked(entry):
            continue
        result.removed.append(str(entry.relative_to(base)) if base else str(entry))
        if not check:
            entry.unlink()


def _resolves_into(catalog: Path) -> Callable[[Path], bool]:
    resolved = catalog.resolve()
    return lambda entry: entry.resolve().parent == resolved


def _points_into(parent: Path) -> Callable[[Path], bool]:
    return lambda entry: Path(os.readlink(entry)).parent == parent


def _points_into_any(*parents: Path) -> Callable[[Path], bool]:
    return lambda entry: Path(os.readlink(entry)).parent in parents


def _blocked(directory: Path, stop: Path) -> Path | None:
    """The first of directory and its parents below `stop` that is there but isn't a folder (a
    file, or a dangling link): links can't go under it."""
    for path in (directory, *directory.parents):
        if path == stop or stop not in path.parents:
            return None
        if (path.is_symlink() or path.exists()) and not path.is_dir():
            return path
    return None


def _sync_links(
    directory: Path,
    targets: dict[str, Path],
    owned: Callable[[Path], bool],
    result: Result,
    *,
    check: bool,
    stop: Path,
    base: Path | None = None,
    ignored: Paths | None = None,
    tracked: Callable[[Path], bool] | None = None,
    owned_paths: set[Path] | None = None,
    recheck: bool = False,
    skills: Sequence[str] = (),
) -> None:
    """Make directory/<name> a symlink to targets[name] for every name. Real files and folders,
    and links this tool didn't make, are kept and reported; so is a new link that `ignored`
    says Git wouldn't ignore. With `recheck`, a link already in place that Git wouldn't ignore
    any more is removed and reported too. A path the repository `tracked` is left alone, with
    a note. `owned_paths` collects the links this tool has afterwards."""

    def label(path: Path) -> str:
        return str(path.relative_to(base)) if base else str(path)

    def refused(path: Path) -> None:
        result.preserved.append(
            f"{label(path)} (Git wouldn't ignore this link; ignore it so the skill can be linked)"
        )

    blocked = _blocked(directory, stop)
    if blocked is not None:
        if targets:
            result.preserved.append(f"{label(blocked)} (not a folder; skill links skipped)")
        return
    changes: list[Path] = []
    current: list[Path] = []
    for name, target in targets.items():
        link = directory / name
        if tracked is not None and tracked(link):
            result.notes.append(
                f"{label(link)}: the repository has its own; the pack's skill isn't linked there"
            )
        elif link.is_symlink() and Path(os.readlink(link)) == target:
            current.append(link)
        elif link.is_symlink() and not owned(link):
            result.preserved.append(
                f"{label(link)} (a link this tool didn't make; remove it so the skill can be "
                f"linked)"
            )
        elif link.exists() and not link.is_symlink():
            result.preserved.append(
                f"{label(link)} (not a link; remove it so the skill can be linked)"
            )
        else:
            changes.append(link)
    asked = changes + (current if recheck else [])
    visible = set(asked) - ignored(asked) if ignored and asked else set()
    for link in current:
        if link in visible:  # Git's rules changed since it was made: take it out again
            result.removed.append(label(link))
            refused(link)
            if not check:
                link.unlink()
            continue
        result.unchanged.append(label(link))
        if owned_paths is not None:
            owned_paths.add(link)
    for link in changes:
        if link in visible:
            if recheck and link.is_symlink():  # this tool's, to an old target: Git shows it
                result.removed.append(label(link))
                if not check:
                    link.unlink()
            refused(link)
            continue
        (result.updated if link.is_symlink() else result.created).append(label(link))
        if owned_paths is not None:
            owned_paths.add(link)
        if check:
            continue
        directory.mkdir(parents=True, exist_ok=True)
        if link.is_symlink():
            link.unlink()
        link.symlink_to(targets[link.name], target_is_directory=True)


def _sync_mirror(standards_root: Path, names: list[str], result: Result, *, check: bool) -> None:
    """Keep <standards>/.claude/skills/<name> as relative links to .agents/skills/<name>."""
    mirror = standards_root / ".claude/skills"
    owned = _points_into(SKILL_MIRROR_TARGET)
    targets = {name: SKILL_MIRROR_TARGET / name for name in names}
    _sync_links(mirror, targets, owned, result, check=check, stop=standards_root)
    _prune_links(mirror, owned, set(names), result, check=check)


@functools.cache
def _repository_variables() -> frozenset[str]:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return frozenset()
    return frozenset(done.stdout.split())


CONFIG_VARIABLES = {"GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT"}  # `git -c`: settings, kept


def git_env() -> dict[str, str]:
    """The environment without the variables that tie Git to one repository (GIT_DIR,
    GIT_INDEX_FILE...): run from a hook or an alias, `git -C <root>` would act on another.
    Settings passed with `git -c` stay."""
    tied = _repository_variables() - CONFIG_VARIABLES
    return {name: value for name, value in os.environ.items() if name not in tied}


def repository_path(root: Path, path: Path) -> str:
    """`path` relative to the repository root, through any symlinked folder above it."""
    return (path.parent.resolve() / path.name).relative_to(root.resolve()).as_posix()


def git_ignores(root: Path) -> Paths:
    """Which of the given paths under root Git would ignore. Without a .git folder (or Git)
    there is nothing to commit them to, so all of them."""

    def ignored(paths: list[Path]) -> set[Path]:
        if not (root / ".git").exists():
            return set(paths)
        relative = {repository_path(root, path): path for path in paths}
        try:
            done = subprocess.run(
                ["git", "-C", str(root), "check-ignore", "--stdin", "-z"],
                input="\0".join(relative).encode(),
                capture_output=True,
                check=False,
                env=git_env(),
            )
        except FileNotFoundError:
            return set(paths)
        listed = {os.fsdecode(item) for item in done.stdout.split(b"\0") if item}
        return {path for key, path in relative.items() if key in listed}

    return ignored


def sync_project_packs(
    root: Path,
    packs: Sequence[str],
    result: Result,
    *,
    check: bool,
    agents_dir: Path,
    ignored: Paths | None = None,
    tracked: Callable[[Path], bool] | None = None,
    owned_paths: set[Path] | None = None,
    recheck: bool = False,
    skills: Sequence[str] = (),
) -> None:
    """Link each skill of the repository's packs into <root>/.claude/skills, for Claude Code, and
    <root>/.agents/skills, for Codex. A new link is made only where Git would ignore it
    (`ignored`, by default Git's answer now), and with `recheck` a link in place that Git
    wouldn't ignore is removed; a path the repository `tracked` is never linked or removed.
    `owned_paths` collects the links this tool has afterwards.

    Links point at <agents_dir>/packs/<name>, normally ~/.agents/packs, so they follow the
    standards repository wherever it lives. Pack skills live there, outside every folder Codex
    reads on its own, so Codex sees them only in repositories with the pack. Links for packs no
    longer listed are removed, unless a listed pack isn't defined: its links can't be told
    apart, so nothing is removed. Links into <agents_dir>/skills, where pack skills used to
    live, are this tool's too, and are replaced. Nothing is linked into a folder that resolves
    outside the repository or into the catalog.
    """
    agents_dir = agents_dir.absolute()  # link targets resolve against the link's own folder
    definitions = load_skill_packs(agents_dir)
    packs_dir, skills_dir = agents_dir / "packs", agents_dir / "skills"
    wanted: dict[str, Path] = {}
    undefined = [pack for pack in packs if pack not in definitions]
    for pack in undefined:
        result.errors.append(
            f"skill pack {pack!r} is listed in the repository's manifest but not defined in "
            f"{agents_dir / SKILL_PACKS_NAME}; its links were left in place"
        )
    for pack in packs:
        for name in definitions.get(pack, []):
            if (packs_dir / name / "SKILL.md").is_file():
                wanted[name] = packs_dir / name
            elif (skills_dir / name / "SKILL.md").is_file():  # a catalog not yet moved
                wanted[name] = skills_dir / name
            else:
                result.errors.append(f"skill pack {pack!r} lists {name!r}, which isn't installed")
    for name in skills:
        # Validate names before joining paths, including hand-edited manifests.
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
            raise ValueError(f"invalid individual skill name: {name!r}")
        if (packs_dir / name / "SKILL.md").is_file():
            wanted[name] = packs_dir / name
        else:
            undefined.append(name)  # preserve existing links when a catalog is incomplete
            result.errors.append(
                f"individual skill {name!r} isn't installed; links were left in place"
            )
    owned = _points_into_any(packs_dir, skills_dir)
    real_root, catalog = root.resolve(), agents_dir.resolve()
    seen: set[Path] = set()
    for relative in (".claude/skills", ".agents/skills"):
        target_dir = root / relative
        if _blocked(target_dir, root) is None:
            real = target_dir.resolve()
            if real in seen:  # .claude/skills -> ../.agents/skills: one folder for both
                continue
            seen.add(real)
            if (
                real == catalog
                or catalog in real.parents
                or (relative == ".agents/skills" and _is_standards_root(root))
            ):
                if wanted:
                    result.preserved.append(
                        f"{relative} (the skill catalog itself, so pack skills aren't linked "
                        f"there; make .agents a folder of this repository's own)"
                    )
                continue
            if real != real_root and real_root not in real.parents:
                if wanted:
                    result.preserved.append(
                        f"{relative} (resolves outside this repository; pack skills aren't "
                        f"linked there)"
                    )
                continue
        _sync_links(
            target_dir,
            dict(sorted(wanted.items())),
            owned,
            result,
            check=check,
            stop=root,
            base=root,
            ignored=ignored or git_ignores(root),
            tracked=tracked,
            owned_paths=owned_paths,
            recheck=recheck,
        )
        if not undefined:
            _prune_links(
                target_dir, owned, set(wanted), result, check=check, base=root, tracked=tracked
            )
        elif target_dir.is_dir():  # an undefined pack's links are kept: still this tool's
            kept = [
                entry
                for entry in sorted(target_dir.iterdir())
                if entry.is_symlink()
                and entry.name not in wanted
                and owned(entry)
                and not (tracked and tracked(entry))
            ]
            shown = set(kept) - (ignored or git_ignores(root))(kept) if recheck and kept else set()
            for entry in kept:
                if entry in shown:  # Git would show it now: take it out
                    result.removed.append(str(entry.relative_to(root)))
                    if not check:
                        entry.unlink()
                elif owned_paths is not None:
                    owned_paths.add(entry)


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


def _sync_global_mcp(
    agents: Path, home: Path, result: Result, *, check: bool, stamp: str, claude: ClaudeMcp | None
) -> None:
    """The global MCP servers, in Claude Code's user scope and ~/.codex/config.toml. With no
    servers in the catalog, the ones installed before are removed."""
    try:
        servers = usable(load_mcp_servers(agents), datetime.now(UTC), result.errors)
    except ValueError as exc:
        result.errors.append(str(exc))
        return
    real = home == Path.home().expanduser().resolve()
    if real and claude_config_elsewhere(home):
        # the portable settings, and so the deny rules, go to ~/.claude/settings.json
        result.notes.append(
            "Claude Code's user-scope MCP servers: skipped (CLAUDE_CONFIG_DIR is set, so Claude "
            "Code doesn't read ~/.claude/settings.json, where their deny rules go)"
        )
        claude = None
        skip_claude = True
    else:
        skip_claude = False
        if claude is None and real:
            claude = ClaudeCli(home)
    cache = str(home / ".cache/repo-template")
    chosen = {name: s for name, s in servers.items() if s.scope == "global"}
    for_claude = {name: s for name, s in chosen.items() if "claude" in s.clients}
    for_codex = {name: s for name, s in chosen.items() if "codex" in s.clients}
    try:
        if not skip_claude:
            sync_claude_mcp(for_claude, claude, home, result, check=check, cache=cache, stamp=stamp)
        sync_codex_mcp(
            for_codex,
            codex_config(home, real),
            home,
            result,
            check=check,
            stamp=stamp,
            cache=cache,
        )
    except ValueError as exc:  # an unreadable globals-state.json
        result.errors.append(f"{exc}; delete it to reset (MCP servers were left alone)")


def _merge_global_gitignore(existing: str) -> str:
    return merge_marked_block(existing, GITIGNORE_CONTENT, GITIGNORE_START, GITIGNORE_END)


def _git_config(home: Path, *args: str) -> str:
    """`git config ARGS` as this machine's Git sees it for `home`, asked from an empty folder
    outside any repository (so an `includeIf` for some repository never decides it); stdout, or
    "" when Git has no answer. For another home (a test's), only that home's config counts."""
    real = home == Path.home().expanduser().resolve()
    env = {**git_env(), "HOME": str(home)}
    if not real:
        for name in ("XDG_CONFIG_HOME", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"):
            env.pop(name, None)
        env["GIT_CONFIG_NOSYSTEM"] = "1"
    with tempfile.TemporaryDirectory() as outside:
        env["GIT_CEILING_DIRECTORIES"] = str(Path(outside).parent)
        try:
            done = subprocess.run(
                ["git", "config", *args],
                capture_output=True,
                text=True,
                check=False,
                env=env,
                cwd=outside,
            )
        except FileNotFoundError:  # no Git
            return ""
    return done.stdout if done.returncode == 0 else ""


def _absolute(named: str, setting: str) -> Path:
    if not Path(named).is_absolute():
        raise ValueError(
            f"{setting} is {named!r}, a relative path that Git reads in each repository; make it "
            f"absolute, then run globals again"
        )
    return Path(named)


def global_ignore_file(home: Path) -> Path:
    """The file Git reads its global ignores from: the one `core.excludesFile` names (in the
    system or global config, or one they include; `~` expanded as Git does), else
    $XDG_CONFIG_HOME/git/ignore, else ~/.config/git/ignore. Raises ValueError for a relative
    excludesFile, which Git reads in each repository."""
    named = _git_config(home, "--includes", "--type=path", "--get", "core.excludesFile").strip()
    if named:
        return _absolute(named, "core.excludesFile")
    real = home == Path.home().expanduser().resolve()
    xdg = os.environ.get("XDG_CONFIG_HOME") if real else None
    return (Path(xdg) if xdg else home / ".config") / "git" / "ignore"


def conditional_ignore_files(home: Path) -> tuple[list[Path], list[str]]:
    """The ignore files Git reads only in some repositories: the core.excludesFile of each file
    an `includeIf` brings in, wherever that includeIf is (the global config, a file it includes,
    or another included file). Also returns a note for each one repo-template leaves alone: a
    relative path, which each repository reads on its own."""
    files: list[Path] = []
    notes: list[str] = []
    seen: set[object] = set()
    scopes: list[tuple[str, ...]] = [("--global",)]
    while scopes:
        listed = _git_config(
            home, *scopes.pop(0), "--includes", "--show-origin", "-z", "--type=path",
            "--get-regexp", r"^includeif\..*\.path$",
        )  # fmt: skip
        records = listed.split("\0")  # file:<origin> NUL <key> LF <value> NUL ...
        for found_in, entry in zip(records[0::2], records[1::2], strict=False):
            key, _, included = entry.partition("\n")
            condition = key[len("includeif.") : -len(".path")]
            holder = Path(found_in.removeprefix("file:"))  # a relative path is relative to it
            source = Path(included) if Path(included).is_absolute() else holder.parent / included
            if _same_file_key(source) in seen:
                continue
            seen.add(_same_file_key(source))
            scopes.append(("--file", str(source)))
            named = _git_config(
                home, "--file", str(source), "--includes", "--type=path", "--get",
                "core.excludesFile",
            ).strip()  # fmt: skip
            if not named:
                continue
            if Path(named).is_absolute():
                files.append(Path(named))
            else:
                notes.append(
                    f"{source} names a relative core.excludesFile ({named}) for repositories "
                    f'matching includeIf "{condition}"; each reads its own, so it is left alone'
                )
    return files, notes


def _same_file_key(path: Path) -> object:
    """What makes two spellings the same file: its device and inode once it exists (through a
    link, a hard link or another case), else its resolved path; the path itself when a link
    loops."""
    try:
        found = path.stat()
        return (found.st_dev, found.st_ino)
    except (OSError, RuntimeError):
        pass
    try:
        return path.resolve()
    except (OSError, RuntimeError):  # a link loop: Python 3.11 and 3.12 raise RuntimeError
        return path


def _writable(path: Path) -> bool:
    """Whether `path` (a file, or where it would be made) can be written by this user."""
    if path.exists():
        return os.access(path, os.W_OK)
    parent = path.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    return os.access(parent, os.W_OK | os.X_OK)


def _sync_global_gitignore(home: Path, result: Result, *, check: bool, stamp: str) -> None:
    """repo-template's block in each file Git reads its global ignores from: the one it always
    reads, and those an `includeIf` names for some repositories. Each is written through a link
    to the file it names, after a backup. A block without both markers, in order, is left
    alone. The always-read file this user can't write is an error (in --check too); one Git
    reads only in some repositories gets a note instead, as it can't be pointed elsewhere."""
    targets: list[tuple[Path, bool]] = []  # each file, and whether Git always reads it
    try:
        targets.append((global_ignore_file(home), True))
    except ValueError as exc:
        result.preserved.append(f"the global Git ignore ({exc})")
    conditional, notes = conditional_ignore_files(home)
    result.notes.extend(notes)
    targets += [(path, False) for path in conditional]
    seen: set[object] = set()
    for path, always in targets:
        if _same_file_key(path) in seen:
            continue
        seen.add(_same_file_key(path))
        try:
            target = path.resolve()  # through a link, to the file it names
            existing = path.read_text() if path.exists() else ""
        except (OSError, RuntimeError, UnicodeDecodeError) as exc:
            result.errors.append(f"cannot read {path}: {exc}")
            continue
        if not marked_block_intact(existing, GITIGNORE_START, GITIGNORE_END):
            result.preserved.append(f"{path} (repo-template's block has lost a marker line; kept)")
            continue
        proposed = _merge_global_gitignore(existing)
        if proposed == existing:
            result.unchanged.append(str(path))
            continue
        if not _writable(target):
            if always:
                result.errors.append(
                    f"cannot write {path} (Git reads its ignores there): add repo-template's "
                    f"block to it yourself, or point a global core.excludesFile at a file you own"
                )
            else:
                result.notes.append(
                    f"{path} (Git reads its ignores there in some repositories) can't be written "
                    f"here: add repo-template's block to it yourself"
                )
            continue
        (result.updated if path.exists() else result.created).append(str(path))
        if check:
            continue
        try:
            if target.exists():
                name = "git-ignore" if len(seen) == 1 else f"git-ignore-{len(seen)}"
                backup = home / ".repo-template" / "backups" / stamp / name
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(proposed)
        except OSError as exc:
            result.errors.append(f"cannot write {path}: {exc.strerror or exc}")


def sync_globals(
    standards_root: Path,
    *,
    home: Path | None = None,
    check: bool = False,
    claude: ClaudeMcp | None = None,
) -> Result:
    """`claude` is Claude Code's user-scope MCP config; by default the `claude` CLI, and only
    for this machine's own home (a test's home gets none unless it passes a fake)."""
    standards_root = find_standards_root(standards_root)
    home = (home or Path.home()).expanduser().resolve()
    result = Result(standards_root)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")

    agents = standards_root / ".agents"
    _link(agents, home / ".agents", result, home=home, stamp=stamp, check=check)
    sync_claude_settings(standards_root, home, result, check=check, stamp=stamp)
    _sync_global_mcp(agents, home, result, check=check, stamp=stamp, claude=claude)

    rewritten = apply_skill_overrides(standards_root, result, check=check)
    skill_root = standards_root / ".agents/skills"
    names = skill_names(standards_root)
    packs = load_skill_packs(standards_root / ".agents")
    in_packs = {name for skills in packs.values() for name in skills}
    unsafe: set[str] = set()
    if _is_full_catalog(standards_root):
        # documents wait for a sound catalog, and a skill with a problem isn't linked
        problems, unsafe = integrity(standards_root, names, rewritten if check else set())
        result.errors.extend(problems)
        if not problems:
            sync_documents(standards_root, names, packs, result, check=check)
    else:  # no provenance to check, but a skill still has to be where it's linked from
        for name, why in placement(standards_root, names, in_packs):
            result.errors.append(f"{name}: {why}")
            unsafe.add(name)
    for missing in sorted(in_packs - set(names)):
        result.errors.append(f"{SKILL_PACKS_NAME} lists {missing!r}, which isn't in the catalog")
    for name in sorted(unsafe - in_packs):
        result.errors.append(f"{name}: not linked until its problems above are fixed")
    global_names = [name for name in names if name not in in_packs and name not in unsafe]
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

    _sync_global_gitignore(home, result, check=check, stamp=stamp)
    return result
