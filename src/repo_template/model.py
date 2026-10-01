from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


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
    policy: str = "managed"
    executable: bool = False


@dataclass
class Result:
    root: Path
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def needs_attention(self) -> bool:
        return bool(self.created or self.updated or self.removed or self.preserved or self.errors)
