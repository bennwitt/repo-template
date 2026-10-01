"""Bring a whole repository to the project baseline: files, Git hook path, and lockfile.

`check` and `update` share this module, so a clean `check` means `update` has nothing to do.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from repo_template.model import Result
from repo_template.scaffold import new_project, skill_packs, update_project
from repo_template.standards import sync_project_packs, unknown_packs

AGENTS_DIR = Path.home() / ".agents"
HOOKS_PATH = ".githooks"
HOOKS_LABEL = f"git config core.hooksPath {HOOKS_PATH}"
LOCK_NAME = "uv.lock"


@dataclass(frozen=True)
class Completed:
    code: int
    out: str = ""
    err: str = ""


class Runner(Protocol):
    """Runs Git and uv. Production uses subprocesses; tests substitute a recording fake."""

    def which(self, program: str) -> bool: ...

    def run(self, args: Sequence[str], cwd: Path) -> Completed: ...


class SubprocessRunner:
    def which(self, program: str) -> bool:
        return shutil.which(program) is not None

    def run(self, args: Sequence[str], cwd: Path) -> Completed:
        process = subprocess.run(list(args), cwd=cwd, check=False, text=True, capture_output=True)
        return Completed(process.returncode, process.stdout, process.stderr)


SUBPROCESS = SubprocessRunner()


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
    result = new_project(
        target, name=name, description=description, python_version=python_version, packs=packs
    )
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
    result = update_project(root, check=check, add_packs=packs)
    wanted = sorted({*skill_packs(result.root), *packs})
    sync_project_packs(result.root, wanted, result, check=check, agents_dir=agents_dir)
    if hooks:
        _reconcile_hooks(result.root, result, runner, check=check)
    if lock:
        _reconcile_lock(result.root, result, runner, check=check)
    return result
