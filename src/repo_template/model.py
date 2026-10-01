from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repo_template.policies import PolicyName


@dataclass(frozen=True)
class ProjectContext:
    project_name: str
    package_name: str
    description: str
    python_version: str

    def substitutions(self) -> dict[str, str]:
        return {
            "__PROJECT_NAME__": self.project_name,
            "__PACKAGE_NAME__": self.package_name,
            "__DESCRIPTION__": self.description,
            "__TOML_DESCRIPTION__": json.dumps(self.description),
            "__PYTHON_VERSION__": self.python_version,
            "__PYTHON_TARGET__": "py" + self.python_version.replace(".", ""),
        }


@dataclass(frozen=True)
class TemplateFile:
    relative_path: str
    content: str
    policy: PolicyName = "managed"
    executable: bool = False
    legacy_path: str | None = None
    legacy_hint: str = ""


@dataclass(frozen=True)
class Conflict:
    """A baseline file that update preserved instead of changing: the person decides.

    `moves_to` is set when `path` is the old name of a baseline file (CONTEXT.md, CLAUDE.md);
    `legacy_baseline` is then what the baseline wants at `path` after the move, if anything.
    """

    path: str
    existing: str
    desired: str
    reason: str = ""
    executable: bool = False
    moves_to: str | None = None
    legacy_baseline: str | None = None


@dataclass
class Result:
    root: Path
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)

    @property
    def needs_attention(self) -> bool:
        return bool(self.created or self.updated or self.removed or self.preserved or self.errors)
