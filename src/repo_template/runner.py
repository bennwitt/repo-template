"""Runs the programs repo-template drives (Git, uv, the Claude Code CLI). Production uses
subprocesses; tests substitute a recording fake."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Completed:
    code: int
    out: str = ""
    err: str = ""


class Runner(Protocol):
    def which(self, program: str) -> bool: ...

    def run(self, args: Sequence[str], cwd: Path) -> Completed: ...


class SubprocessRunner:
    def __init__(self, env: Mapping[str, str] | None = None, timeout: float | None = None) -> None:
        self.env = dict(env) if env is not None else None
        self.timeout = timeout

    def which(self, program: str) -> bool:
        return shutil.which(program) is not None

    def run(self, args: Sequence[str], cwd: Path) -> Completed:
        try:
            process = subprocess.run(
                list(args),
                cwd=cwd,
                check=False,
                text=True,
                capture_output=True,
                env={**os.environ, **self.env} if self.env is not None else None,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return Completed(124, "", f"{args[0]} timed out after {self.timeout} s")
        return Completed(process.returncode, process.stdout, process.stderr)


SUBPROCESS = SubprocessRunner()
