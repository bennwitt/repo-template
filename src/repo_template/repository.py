"""Bring a whole repository to the project baseline: files, Git hook path, and lockfile.

`check` and `update` share this module, so a clean `check` means `update` has nothing to do.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from repo_template.mcp import Server, for_packs, load_mcp_servers, pack_servers, usable
from repo_template.mcp_project import (
    McpPlan,
    apply_codex_mcp,
    apply_project_mcp,
    kept_mcp,
    plan_codex_mcp,
    plan_project_mcp,
    recorded_mcp,
)
from repo_template.model import Result
from repo_template.runner import SUBPROCESS, Completed, Runner, SubprocessRunner
from repo_template.scaffold import new_project, read_manifest, skill_packs, update_project
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
        raise ValueError(
            f"unknown skill pack: {', '.join(unknown)} (see {agents_dir / 'skill-packs.json'})"
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
    root: Path, packs: Sequence[str], agents_dir: Path, manifest: dict[str, Any]
) -> _Mcp | None:
    """None for a repository with no packs and no MCP records, which needs no MCP catalog (CI
    has no ~/.agents)."""
    if not packs and not recorded_mcp(manifest) and not kept_mcp(manifest):
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


def _sync_codex(root: Path, mcp: _Mcp | None, result: Result, *, check: bool) -> None:
    """After the baseline: its .gitignore decides whether the Codex file may be written."""
    if mcp is None:
        return
    # in check mode the .gitignore isn't written yet; the baseline's ignores .codex/
    ignored = True if check and ".gitignore" in result.created + result.updated else None
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
    runner: Runner = SUBPROCESS,
    agents_dir: Path = AGENTS_DIR,
) -> Result:
    """Render the baseline into an empty directory, then initialize Git and the lockfile."""
    _require_known_packs(packs, agents_dir)
    mcp = _mcp(target.resolve(), list(packs), agents_dir, {})
    plan = _plan_claude(target.resolve(), mcp, {})
    result = new_project(
        target,
        name=name,
        description=description,
        python_version=python_version,
        packs=packs,
        mcp=plan.manifest if plan else None,
    )
    if plan:
        apply_project_mcp(result.root, plan, result, check=False)
    _sync_codex(result.root, mcp, result, check=False)
    if mcp:
        result.errors.extend(mcp.errors)
    sync_project_packs(result.root, packs, result, check=False, agents_dir=agents_dir)
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


def update_repository(
    root: Path,
    *,
    check: bool = False,
    hooks: bool = True,
    lock: bool = True,
    packs: Sequence[str] = (),
    runner: Runner = SUBPROCESS,
    agents_dir: Path = AGENTS_DIR,
) -> Result:
    """Plan (check=True) or apply every change that brings `root` to the baseline.

    `packs` adds skill packs to the repository's manifest; every listed pack is then linked.
    """
    _require_known_packs(packs, agents_dir)
    manifest = read_manifest(root)
    wanted = sorted({*skill_packs(root.resolve()), *packs})
    mcp = _mcp(root.resolve(), wanted, agents_dir, manifest)
    plan = _plan_claude(root.resolve(), mcp, manifest)
    first = Result(root.resolve())
    if plan:  # .mcp.json first: the manifest written next records only what was written
        apply_project_mcp(root.resolve(), plan, first, check=check)
    result = update_project(root, check=check, add_packs=packs, mcp=plan.manifest if plan else None)
    _merge(first, result)
    if mcp:
        result.errors.extend(mcp.errors)
    _sync_codex(result.root, mcp, result, check=check)
    sync_project_packs(result.root, wanted, result, check=check, agents_dir=agents_dir)
    if hooks:
        _reconcile_hooks(result.root, result, runner, check=check)
    if lock:
        _reconcile_lock(result.root, result, runner, check=check)
    return result
