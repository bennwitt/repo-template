"""Bring a whole repository to the project baseline: files, Git hook path, and lockfile.

`check` and `update` share this module, so a clean `check` means `update` has nothing to do.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from repo_template.mcp import Server, for_packs, load_mcp_servers, pack_servers, usable
from repo_template.mcp_globals import (
    CLAUDE_STATE,
    ClaudeCli,
    ClaudeMcp,
    claude_config_elsewhere,
    sync_claude_mcp,
)
from repo_template.mcp_project import (
    BLOCK,
    CODEX_FILE,
    McpPlan,
    apply_codex_mcp,
    apply_project_mcp,
    kept_mcp,
    plan_codex_mcp,
    plan_project_mcp,
    recorded_mcp,
)
from repo_template.model import Result
from repo_template.personal import (
    Index,
    apply_exclude,
    codex_choice,
    exclude_patterns,
    listed_paths,
    plan_exclude,
    predicted_ignores,
    sparse,
    team_servers,
    tracked_paths,
)
from repo_template.runner import SUBPROCESS, Completed, Runner, SubprocessRunner
from repo_template.scaffold import (
    PACKS_ONLY,
    PERSONAL,
    new_project,
    preflight,
    update_packs_only,
    update_project,
)
from repo_template.selection import Selection, require_skills
from repo_template.standards import load_skill_packs, sync_project_packs, unknown_packs

AGENTS_DIR = Path.home() / ".agents"
HOOKS_PATH = ".githooks"
HOOKS_LABEL = f"git config core.hooksPath {HOOKS_PATH}"
LOCK_NAME = "uv.lock"
__all__ = [
    "SUBPROCESS",
    "Completed",
    "Runner",
    "SubprocessRunner",
    "create_repository",
    "update_repository",
]


def _reconcile_hooks(root: Path, result: Result, runner: Runner, *, check: bool) -> None:
    if not (root / ".git").exists():
        return
    if not runner.which("git"):
        if not check:
            result.errors.append("git is not installed; core.hooksPath was not configured")
        return
    current = runner.run(["git", "config", "--get", "core.hooksPath"], root)
    if current.code == 0 and current.out.strip() == HOOKS_PATH:
        return
    bucket = result.updated if current.code == 0 else result.created
    if check:
        bucket.append(HOOKS_LABEL)
        return
    done = runner.run(["git", "config", "core.hooksPath", HOOKS_PATH], root)
    if done.code:
        result.errors.append(done.err.strip() or "could not configure Git hooks")
        return
    bucket.append(HOOKS_LABEL)


def _reconcile_lock(root: Path, result: Result, runner: Runner, *, check: bool) -> None:
    lock = root / LOCK_NAME
    pyproject_changed = "pyproject.toml" in result.created or "pyproject.toml" in result.updated
    if lock.exists() and not pyproject_changed:
        return
    bucket = result.updated if lock.exists() else result.created
    if check:
        bucket.append(LOCK_NAME)
        return
    if not runner.which("uv"):
        result.errors.append("uv is not installed; run `uv lock` after installing it")
        return
    before = lock.read_bytes() if lock.exists() else None
    done = runner.run(["uv", "lock"], root)
    if done.code:
        result.errors.append(done.err.strip() or "uv lock failed")
        return
    if not lock.exists() or lock.read_bytes() != before:
        bucket.append(LOCK_NAME)


def _require_known_packs(packs: Sequence[str], agents_dir: Path) -> None:
    unknown = unknown_packs(packs, agents_dir)
    if unknown:
        known = ", ".join(sorted(load_skill_packs(agents_dir))) or "none defined"
        raise ValueError(
            f"unknown skill pack: {', '.join(unknown)} (the packs: {known}; see "
            f"{agents_dir / 'skill-packs.json'})"
        )


@dataclass
class _Mcp:
    """The pack MCP servers a repository's packs use, and how to plan them."""

    servers: dict[str, Server]
    owned: set[str]
    removals: bool
    cache: str
    errors: list[str] = field(default_factory=list)  # servers held back, and why


def _mcp(
    root: Path,
    packs: Sequence[str],
    agents_dir: Path,
    manifest: dict[str, Any],
    *,
    always: bool = False,
) -> _Mcp | None:
    """None for a repository with no packs and no MCP records, which needs no MCP catalog (CI
    has no ~/.agents); `always` for one whose records live elsewhere (personal)."""
    if not always and not packs and not recorded_mcp(manifest) and not kept_mcp(manifest):
        return None
    servers = load_mcp_servers(agents_dir)
    definitions = load_skill_packs(agents_dir)
    known = [pack for pack in packs if pack in definitions]
    owned = manifest.get("project_owned", [])
    errors: list[str] = []
    wanted = for_packs(known, servers, pack_servers(agents_dir, servers))
    return _Mcp(
        usable(wanted, datetime.now(UTC), errors),
        {item for item in owned if isinstance(item, str)} if isinstance(owned, list) else set(),
        removals=len(known) == len(packs),
        cache=str(Path.home() / ".cache/repo-template"),
        errors=errors,
    )


def _plan_claude(root: Path, mcp: _Mcp | None, manifest: dict[str, Any]) -> McpPlan | None:
    if mcp is None:
        return None
    return plan_project_mcp(root, mcp.servers, manifest, owned=mcp.owned, removals=mcp.removals)


def _sync_codex(
    root: Path, mcp: _Mcp | None, result: Result, *, check: bool, ignored: bool | None = None
) -> None:
    """After the baseline: its .gitignore decides whether the Codex file may be written.
    `ignored`: Git's answer for the file, when the caller knows it better than Git does now."""
    if mcp is None:
        return
    if ignored is None and check and ".gitignore" in result.created + result.updated:
        ignored = True  # in check mode the .gitignore isn't written yet; the baseline's ignores it
    plan = plan_codex_mcp(
        root, mcp.servers, owned=mcp.owned, removals=mcp.removals, cache=mcp.cache, ignored=ignored
    )
    apply_codex_mcp(root, plan, result, check=check)


def create_repository(
    target: Path,
    *,
    name: str,
    description: str,
    python_version: str,
    git: bool = True,
    lock: bool = True,
    packs: Sequence[str] = (),
    skills: Sequence[str] = (),
    runner: Runner = SUBPROCESS,
    agents_dir: Path = AGENTS_DIR,
) -> Result:
    """Render the baseline into an empty directory, then initialize Git and the lockfile."""
    _require_known_packs(packs, agents_dir)
    require_skills(skills, agents_dir)
    mcp = _mcp(target.resolve(), list(packs), agents_dir, {})
    plan = _plan_claude(target.resolve(), mcp, {})
    result = new_project(
        target,
        name=name,
        description=description,
        python_version=python_version,
        packs=packs,
        skills=skills,
        mcp=plan.manifest if plan else None,
    )
    if plan:
        apply_project_mcp(result.root, plan, result, check=False)
    _sync_codex(result.root, mcp, result, check=False)
    if mcp:
        result.errors.extend(mcp.errors)
    sync_project_packs(
        result.root, packs, result, check=False, agents_dir=agents_dir, skills=skills
    )
    if git:
        if not runner.which("git"):
            result.errors.append("git is not installed; repository files were still created")
        else:
            done = runner.run(["git", "init", "-b", "main"], result.root)
            if done.code:
                result.errors.append(done.err.strip() or "git init failed")
            else:
                _reconcile_hooks(result.root, result, runner, check=False)
    if lock:
        _reconcile_lock(result.root, result, runner, check=False)
    return result


def _merge(first: Result, result: Result) -> None:
    """Put `first`'s lines ahead of `result`'s, as if one step had made them all."""
    for name in ("created", "updated", "unchanged", "preserved", "removed", "errors", "notes"):
        getattr(result, name)[:0] = getattr(first, name)


def local_claude(root: Path, home: Path) -> ClaudeMcp | None:
    """Claude Code's local scope for the checkout at `root`, through the `claude` CLI. Tests
    replace this (tests/conftest.py), so none of them reaches this machine's ~/.claude.json."""
    return ClaudeCli(home, project=root)


def _codex_stays(root: Path, mcp: _Mcp) -> bool:
    """Whether repo-template's block is in .codex/config.toml after the run (planned as if Git
    ignored the file, which the exclude block makes so)."""
    plan = plan_codex_mcp(
        root, mcp.servers, owned=mcp.owned, removals=mcp.removals, cache=mcp.cache, ignored=True
    )
    if plan.delete:
        return False
    if plan.text is not None:
        return BLOCK.search(plan.text) is not None
    try:
        return BLOCK.search((root / CODEX_FILE).read_text()) is not None
    except (OSError, UnicodeDecodeError):
        return False


def _sync_claude_local(
    root: Path,
    mcp: _Mcp,
    result: Result,
    *,
    check: bool,
    claude: ClaudeMcp | None,
    home: Path,
    fresh: bool,
) -> None:
    """The packs' servers in Claude Code's local scope for this checkout, never in .mcp.json.
    One the repository's .mcp.json defines is the team's: the pack's isn't added."""
    servers = {name: s for name, s in mcp.servers.items() if "claude" in s.clients}
    for name in sorted(set(servers) & team_servers(root)):
        result.notes.append(
            f".mcp.json defines {name}, so the pack's isn't added (approve the repository's in "
            f"Claude Code to use it)"
        )
        del servers[name]
    if claude_config_elsewhere(home):
        result.notes.append(
            "Claude Code's local-scope MCP servers: skipped (CLAUDE_CONFIG_DIR is set, so Claude "
            "Code doesn't read ~/.claude/settings.json, where their deny rules go)"
        )
        return
    claude = claude or local_claude(root, home)
    try:
        sync_claude_mcp(
            servers,
            claude,
            home,
            result,
            check=check,
            cache=mcp.cache,
            stamp=datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f"),
            scope="local",
            state_key=f"{CLAUDE_STATE}:local:{root}",  # by path: a moved checkout starts afresh
            label=f"{claude.path} projects[{root}].mcpServers" if claude else None,
            removals=mcp.removals,
            fresh=fresh,
        )
    except ValueError as exc:  # an unreadable globals-state.json
        result.errors.append(f"{exc}; delete it to reset (MCP servers were left alone)")


def _links_under_tracked_folders(root: Path, index: Index, agents_dir: Path) -> list[Path]:
    """Links of this tool's at a path the repository tracks only around it (its files not checked
    out, or a submodule mounted above it): the repository's version isn't there, and the link
    stands in its way."""
    agents = agents_dir.absolute()
    homes = {agents / "packs", agents / "skills"}
    found: list[Path] = []
    seen: set[Path] = set()  # .claude/skills may be a link to .agents/skills
    for folder in (".claude/skills", ".agents/skills"):
        directory = root / folder
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            real = entry.parent.resolve() / entry.name
            if (
                entry.is_symlink()
                and Path(os.readlink(entry)).parent in homes
                and index.only_under(entry)
                and real not in seen
            ):
                seen.add(real)
                found.append(entry)
    return found


def _update_personal(
    root: Path,
    manifest: dict[str, Any],
    selection: Selection,
    *,
    packs: Sequence[str],
    skills: Sequence[str],
    remove_packs: Sequence[str],
    remove_skills: Sequence[str],
    check: bool,
    agents_dir: Path,
    claude: ClaudeMcp | None,
    home: Path,
) -> Result:
    """A personal adoption (see repo_template.personal). Everything is worked out, and every
    file read, before the first write; the exclude block is written before the links and the
    Codex file it ignores."""
    if sparse(root):
        raise ValueError(
            f"{root} is a sparse checkout: repository files outside it can land where a link or "
            f"the Codex file stands, so personal adoption isn't supported here (`git "
            f"sparse-checkout disable` first)"
        )
    wanted = selection.packs
    mcp = _mcp(root, wanted, agents_dir, manifest, always=True)
    assert mcp is not None
    tracked = tracked_paths(root)
    links: set[Path] = set()
    sync_project_packs(  # a dry run, as if Git ignored every link: which ones this tool will have
        root,
        wanted,
        Result(root),
        check=True,
        agents_dir=agents_dir,
        ignored=lambda paths: set(paths),
        tracked=tracked,
        owned_paths=links,
        skills=selection.skills,
    )
    codex = root / CODEX_FILE
    mode, why = codex_choice(root, tracked)
    # "remove": take repo-template's whole block out (every server in it is ours), since Git
    # would show the file; whatever stays in it stays listed
    for_codex = mcp if mode == "sync" else replace(mcp, servers={}, removals=True)
    probe = Result(root)
    stays = mode != "skip" and _codex_stays(root, for_codex)
    patterns = exclude_patterns(root, links, stays, probe)
    exclude = plan_exclude(root, patterns)
    ignored = predicted_ignores(root, set() if exclude.damaged else listed_paths(patterns))
    codex_ignored = mode == "remove" or codex in ignored([codex])

    result = update_packs_only(
        root,
        check=check,
        add_packs=packs,
        add_skills=skills,
        remove_packs=remove_packs,
        remove_skills=remove_skills,
        profile=PERSONAL,
    )
    result.errors.extend(mcp.errors + probe.errors)
    stale = _links_under_tracked_folders(root, tracked, agents_dir)
    for link in stale:  # the repository's own version belongs there
        result.removed.append(link.relative_to(root).as_posix())
        if not check:
            link.unlink()
    apply_exclude(exclude, result, check=check)
    if why:
        result.notes.append(why)
    if mode != "skip":
        _sync_codex(root, for_codex, result, check=check, ignored=codex_ignored)
    sync_project_packs(
        root,
        wanted,
        result,
        check=check,
        agents_dir=agents_dir,
        ignored=ignored,
        tracked=tracked,
        recheck=True,
        skills=selection.skills,
    )
    _sync_claude_local(root, mcp, result, check=check, claude=claude, home=home, fresh=not manifest)
    return result


def update_repository(
    root: Path,
    *,
    check: bool = False,
    hooks: bool = True,
    lock: bool = True,
    packs: Sequence[str] = (),
    skills: Sequence[str] = (),
    remove_packs: Sequence[str] = (),
    remove_skills: Sequence[str] = (),
    runner: Runner = SUBPROCESS,
    agents_dir: Path = AGENTS_DIR,
    packs_only: bool = False,
    personal: bool = False,
    claude: ClaudeMcp | None = None,
    home: Path | None = None,
) -> Result:
    """Plan (check=True) or apply every change that brings `root` to the baseline.

    `packs` adds skill packs to the repository's manifest; every listed pack is then linked.
    `packs_only` adopts a repository for its packs alone (its manifest then says so, and later
    runs follow it): no baseline file, hook path or lockfile. `personal` adopts it for its packs
    for this user alone, changing nothing anyone else sees (see repo_template.personal);
    `claude` and `home` are where its Claude Code servers go, this machine's by default.
    """
    _require_known_packs(packs, agents_dir)
    require_skills(skills, agents_dir)
    # every refusal before the first write (.mcp.json is written ahead of the manifest)
    manifest = preflight(
        root, packs_only=packs_only, personal=personal, add_packs=packs, add_skills=skills
    )
    selection = Selection.from_manifest(manifest).change(packs, skills, remove_packs, remove_skills)
    if personal or manifest.get("profile") == PERSONAL:
        home = (home or Path.home()).expanduser().resolve()
        return _update_personal(
            root.resolve(),
            manifest,
            selection,
            packs=packs,
            skills=skills,
            remove_packs=remove_packs,
            remove_skills=remove_skills,
            check=check,
            agents_dir=agents_dir,
            claude=claude,
            home=home,
        )
    packs_only = packs_only or manifest.get("profile") == PACKS_ONLY
    wanted = selection.packs
    mcp = _mcp(root.resolve(), wanted, agents_dir, manifest)
    plan = _plan_claude(root.resolve(), mcp, manifest)
    first = Result(root.resolve())
    if plan:  # .mcp.json first: the manifest written next records only what was written
        apply_project_mcp(root.resolve(), plan, first, check=check)
    update = update_packs_only if packs_only else update_project
    result = update(
        root,
        check=check,
        add_packs=packs,
        add_skills=skills,
        remove_packs=remove_packs,
        remove_skills=remove_skills,
        mcp=plan.manifest if plan else None,
    )
    _merge(first, result)
    if mcp:
        result.errors.extend(mcp.errors)
    _sync_codex(result.root, mcp, result, check=check)
    sync_project_packs(
        result.root, wanted, result, check=check, agents_dir=agents_dir, skills=selection.skills
    )
    if packs_only:
        return result
    if hooks:
        _reconcile_hooks(result.root, result, runner, check=check)
    if lock:
        _reconcile_lock(result.root, result, runner, check=check)
    return result
