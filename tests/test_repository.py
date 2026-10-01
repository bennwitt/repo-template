from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from repo_template.repository import (
    HOOKS_LABEL,
    Completed,
    create_repository,
    update_repository,
)
from repo_template.scaffold import new_project


class FakeRunner:
    """Simulates Git config state and `uv lock` so tests can observe every external call."""

    def __init__(self, *, missing: Sequence[str] = ()) -> None:
        self.missing = set(missing)
        self.calls: list[list[str]] = []
        self.hooks_path: str | None = None

    def which(self, program: str) -> bool:
        return program not in self.missing

    def run(self, args: Sequence[str], cwd: Path) -> Completed:
        command = list(args)
        self.calls.append(command)
        if command[:2] == ["git", "init"]:
            (cwd / ".git").mkdir()
            return Completed(0)
        if command[:3] == ["git", "config", "--get"]:
            if self.hooks_path is None:
                return Completed(1)
            return Completed(0, self.hooks_path + "\n")
        if command[:2] == ["git", "config"]:
            self.hooks_path = command[3]
            return Completed(0)
        if command == ["uv", "lock"]:
            (cwd / "uv.lock").write_text("version = 1\n")
            return Completed(0)
        raise AssertionError(f"unexpected command: {command}")

    @property
    def writes(self) -> list[list[str]]:
        return [call for call in self.calls if call[:3] != ["git", "config", "--get"]]


def _bare_repository(root: Path) -> Path:
    new_project(root, name=root.name, description="Sample.", python_version="3.12")
    (root / ".git").mkdir()
    return root


def test_check_reports_what_update_then_fixes(tmp_path: Path) -> None:
    root = _bare_repository(tmp_path / "sample")
    runner = FakeRunner()

    planned = update_repository(root, check=True, runner=runner)

    assert planned.created == [HOOKS_LABEL, "uv.lock"]
    assert runner.writes == []
    assert not (root / "uv.lock").exists()

    applied = update_repository(root, runner=runner)

    assert applied.created == planned.created
    assert runner.writes == [["git", "config", "core.hooksPath", ".githooks"], ["uv", "lock"]]
    assert not update_repository(root, check=True, runner=runner).needs_attention


def test_lock_is_refreshed_when_pyproject_changes(tmp_path: Path) -> None:
    root = _bare_repository(tmp_path / "sample")
    runner = FakeRunner()
    update_repository(root, runner=runner)
    pyproject = root / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('    "pytest-cov>=7.0",\n', ""))
    (root / "uv.lock").write_text("stale\n")

    planned = update_repository(root, check=True, runner=runner)
    applied = update_repository(root, runner=runner)

    assert "uv.lock" in planned.updated
    assert "uv.lock" in applied.updated
    assert (root / "uv.lock").read_text() == "version = 1\n"


def test_disabled_steps_make_no_external_calls(tmp_path: Path) -> None:
    root = _bare_repository(tmp_path / "sample")
    runner = FakeRunner()

    result = update_repository(root, hooks=False, lock=False, runner=runner)

    assert runner.calls == []
    assert HOOKS_LABEL not in result.created
    assert "uv.lock" not in result.created


def test_missing_tools_are_errors_when_applying(tmp_path: Path) -> None:
    root = _bare_repository(tmp_path / "sample")
    runner = FakeRunner(missing=["git", "uv"])

    planned = update_repository(root, check=True, runner=runner)
    applied = update_repository(root, runner=runner)

    assert planned.errors == []
    assert any("git is not installed" in error for error in applied.errors)
    assert any("uv is not installed" in error for error in applied.errors)


def test_create_repository_initializes_git_hooks_and_lock(tmp_path: Path) -> None:
    runner = FakeRunner()

    result = create_repository(
        tmp_path / "fresh",
        name="fresh",
        description="Fresh.",
        python_version="3.12",
        runner=runner,
    )

    assert not result.errors
    assert runner.writes == [
        ["git", "init", "-b", "main"],
        ["git", "config", "core.hooksPath", ".githooks"],
        ["uv", "lock"],
    ]
    assert {HOOKS_LABEL, "uv.lock"} <= set(result.created)
    assert not update_repository(result.root, check=True, runner=runner).needs_attention


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_hook_path_with_real_git(tmp_path: Path) -> None:
    result = create_repository(
        tmp_path / "real", name="real", description="Real.", python_version="3.12", lock=False
    )
    configured = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=result.root,
        text=True,
        capture_output=True,
        check=True,
    )

    assert configured.stdout.strip() == ".githooks"
    assert not update_repository(result.root, check=True, lock=False).needs_attention
