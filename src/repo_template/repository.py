"""Bring a whole repository to the project baseline: files, Git hook path, and lockfile.

`check` and `update` share this module, so a clean `check` means `update` has nothing to do.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from repo_template.mcp import for_packs, load_mcp_servers, pack_servers
from repo_template.mcp_project import McpPlan, apply_project_mcp, plan_project_mcp, recorded_mcp
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


def _mcp_plan(
    root: Path, packs: Sequence[str], agents_dir: Path, manifest: dict[str, Any]
) -> McpPlan | None:
    """The pack MCP servers' plan; None for a repository with no packs and no recorded servers,
    which needs no MCP catalog (CI has no ~/.agents)."""
    recorded = recorded_mcp(manifest)
    if not packs and not recorded:
        return None
    servers = load_mcp_servers(agents_dir)
    definitions = load_skill_packs(agents_dir)
    known = [pack for pack in packs if pack in definitions]
    wanted = for_packs(known, servers, pack_servers(agents_dir, servers))
    owned = manifest.get("project_owned", [])
    return plan_project_mcp(
        root,
        wanted,
        recorded,
        owned={item for item in owned if isinstance(item, str)}
        if isinstance(owned, list)
        else set(),
        removals=len(known) == len(packs),
        cache=str(Path.home() / ".cache/repo-template"),
    )


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
    plan = _mcp_plan(target.resolve(), list(packs), agents_dir, {})
    result = new_project(
        target,
        name=name,
        description=description,
        python_version=python_version,
        packs=packs,
        mcp_servers=plan.record if plan else None,
    )
    if plan:
        apply_project_mcp(result.root, plan, result, check=False)
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
    wanted = sorted({*skill_packs(root.resolve()), *packs})
    plan = _mcp_plan(root.resolve(), wanted, agents_dir, read_manifest(root))
    result = update_project(
        root, check=check, add_packs=packs, mcp_servers=plan.record if plan else None
    )
    if plan:
        apply_project_mcp(result.root, plan, result, check=check)
    sync_project_packs(result.root, wanted, result, check=check, agents_dir=agents_dir)
    if hooks:
        _reconcile_hooks(result.root, result, runner, check=check)
    if lock:
        _reconcile_lock(result.root, result, runner, check=check)
    return result
