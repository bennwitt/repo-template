"""What `new` and `update` may do to each baseline file: one policy per kind of file.

Every policy answers the same question through `decide`: given the file on disk (or None), the
content the baseline wants, and the hash recorded when the file was last generated, should the
file be created, upgraded, left unchanged, or preserved for manual review, and with what content?
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Protocol

PolicyName = Literal["managed", "seed", "gitignore", "json_merge", "toml_merge"]

GITIGNORE_START = "# >>> repo-template managed defaults"
GITIGNORE_END = "# <<< repo-template managed defaults"


class Outcome(Enum):
    CREATE = "create"
    UPGRADE = "upgrade"
    UNCHANGED = "unchanged"
    PRESERVE = "preserve"


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    content: str = ""
    note: str = ""


class Policy(Protocol):
    def decide(self, existing: str | None, desired: str, recorded: str | None) -> Decision: ...

    def record(self, existing: str, desired: str) -> str | None:
        """The hash to keep in the manifest for this file, or None."""
        ...


def digest(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def merge_marked_block(existing: str, content: str, start: str, end: str) -> str:
    """Replace the block between `start` and `end` markers, or append it after a blank line."""
    block = f"{start}\n{content.rstrip()}\n{end}\n"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
    if pattern.search(existing):
        return pattern.sub(lambda _: block, existing, count=1)
    prefix = existing.rstrip()
    return f"{prefix}\n\n{block}" if prefix else block


def _merge_gitignore(existing: str, desired: str) -> str:
    return merge_marked_block(existing, desired, GITIGNORE_START, GITIGNORE_END)


def _merge_json_value(existing: Any, desired: Any, *, key: str = "") -> Any:
    if isinstance(existing, dict) and isinstance(desired, dict):
        merged = dict(existing)
        for child_key, child_value in desired.items():
            if child_key in merged:
                merged[child_key] = _merge_json_value(merged[child_key], child_value, key=child_key)
            else:
                merged[child_key] = child_value
        return merged
    if isinstance(existing, list) and isinstance(desired, list):
        if key == "tasks":
            labels = {
                item.get("label")
                for item in existing
                if isinstance(item, dict) and isinstance(item.get("label"), str)
            }
            return existing + [
                item
                for item in desired
                if not isinstance(item, dict) or item.get("label") not in labels
            ]
        return existing + [item for item in desired if item not in existing]
    return existing


def _merge_json(existing: str, desired: str) -> str:
    old_value = json.loads(existing)
    new_value = json.loads(desired)
    merged = _merge_json_value(old_value, new_value)
    return json.dumps(merged, indent=2, ensure_ascii=False) + "\n"


def _dependency_name(specifier: str) -> str:
    match = re.match(r"[A-Za-z0-9_.-]+", specifier)
    return match.group(0).lower().replace("_", "-") if match else specifier.lower()


def _table_block(content: str, table: str) -> str | None:
    pattern = re.compile(
        rf"(?ms)^\[{re.escape(table)}\]\n.*?(?=^\[|\Z)",
    )
    match = pattern.search(content)
    return match.group(0).rstrip() if match else None


def _append_dev_dependencies(content: str, required: list[str]) -> str:
    parsed = tomllib.loads(content)
    present_specs: list[str] = []
    project = parsed.get("project", {})
    if isinstance(project, dict) and isinstance(project.get("dependencies"), list):
        present_specs.extend(str(item) for item in project["dependencies"])
    groups = parsed.get("dependency-groups", {})
    if isinstance(groups, dict) and isinstance(groups.get("dev"), list):
        present_specs.extend(str(item) for item in groups["dev"])
    tool = parsed.get("tool", {})
    if isinstance(tool, dict):
        uv = tool.get("uv", {})
        if isinstance(uv, dict) and isinstance(uv.get("dev-dependencies"), list):
            present_specs.extend(str(item) for item in uv["dev-dependencies"])
    present = {_dependency_name(item) for item in present_specs}
    missing = [item for item in required if _dependency_name(item) not in present]
    if not missing:
        return content

    section = re.search(r"(?ms)^\[dependency-groups\]\n.*?(?=^\[|\Z)", content)
    if section is None:
        entries = "\n".join(f'    "{item}",' for item in missing)
        return content.rstrip() + f"\n\n[dependency-groups]\ndev = [\n{entries}\n]\n"

    section_text = section.group(0)
    dev = re.search(r"(?ms)^dev\s*=\s*\[(.*?)\]", section_text)
    if dev is None:
        entries = "\n".join(f'    "{item}",' for item in missing)
        insertion = f"dev = [\n{entries}\n]\n"
        return content[: section.end()] + insertion + content[section.end() :]

    inner_start = section.start() + dev.start(1)
    inner_end = section.start() + dev.end(1)
    inner = content[inner_start:inner_end]
    stripped = inner.rstrip()
    if "\n" in inner:
        separator = "" if not stripped or stripped.endswith(",") else ","
        addition = separator + "\n" + "\n".join(f'    "{item}",' for item in missing)
        replacement = stripped + addition + "\n"
    else:
        separator = "" if not stripped or stripped.endswith(",") else ","
        addition = ", ".join(f'"{item}"' for item in missing)
        replacement = stripped + separator + (" " if stripped else "") + addition
    return content[:inner_start] + replacement + content[inner_end:]


def _merge_pyproject(existing: str, desired: str) -> str:
    desired_data = tomllib.loads(desired)
    groups = desired_data.get("dependency-groups", {})
    required = groups.get("dev", []) if isinstance(groups, dict) else []
    proposed = _append_dev_dependencies(existing, [str(item) for item in required])
    configured = tomllib.loads(existing).get("tool", {})
    for table in ("tool.pytest.ini_options", "tool.ruff", "tool.ruff.lint", "tool.mypy"):
        # A tool the project already configures keeps its settings: adding even one table
        # (say a line length beside an existing [tool.ruff.lint]) changes how the tool behaves.
        if table.split(".")[1] in configured:
            continue
        block = _table_block(desired, table)
        if block:
            proposed = proposed.rstrip() + "\n\n" + block + "\n"
    tomllib.loads(proposed)
    return proposed


def _compare(existing: str, proposed: str) -> Decision:
    if existing == proposed:
        return Decision(Outcome.UNCHANGED, existing)
    return Decision(Outcome.UPGRADE, proposed)


class Managed:
    """Owned by the baseline: upgraded only while unchanged since it was generated."""

    def decide(self, existing: str | None, desired: str, recorded: str | None) -> Decision:
        if existing is None:
            return Decision(Outcome.CREATE, desired)
        if existing == desired:
            return Decision(Outcome.UNCHANGED, existing)
        if recorded == digest(existing):
            return Decision(Outcome.UPGRADE, desired)
        return Decision(Outcome.PRESERVE)

    def record(self, existing: str, desired: str) -> str | None:
        return digest(existing) if existing == desired else None


class Seed:
    """A starting point: written once if missing, then owned by the project."""

    def decide(self, existing: str | None, desired: str, recorded: str | None) -> Decision:
        if existing is None:
            return Decision(Outcome.CREATE, desired)
        return Decision(Outcome.UNCHANGED, existing)

    def record(self, existing: str, desired: str) -> str | None:
        return None


class GitignoreBlock:
    """Keeps the baseline's ignore rules in a marked block and leaves the rest alone."""

    def decide(self, existing: str | None, desired: str, recorded: str | None) -> Decision:
        if existing is None:
            return Decision(Outcome.CREATE, _merge_gitignore("", desired))
        return _compare(existing, _merge_gitignore(existing, desired))

    def record(self, existing: str, desired: str) -> str | None:
        return None


class JsonMerge:
    """Adds missing keys, list items and VS Code tasks; never removes anything."""

    def decide(self, existing: str | None, desired: str, recorded: str | None) -> Decision:
        if existing is None:
            normalized = json.dumps(json.loads(desired), indent=2, ensure_ascii=False) + "\n"
            return Decision(Outcome.CREATE, normalized)
        try:
            return _compare(existing, _merge_json(existing, desired))
        except json.JSONDecodeError:
            return Decision(Outcome.PRESERVE, note="invalid JSON")

    def record(self, existing: str, desired: str) -> str | None:
        return None


class TomlMerge:
    """Adds missing dev dependencies, and tool tables for tools the project doesn't configure.

    Never touches project metadata or an existing tool's settings.
    """

    def decide(self, existing: str | None, desired: str, recorded: str | None) -> Decision:
        if existing is None:
            return Decision(Outcome.CREATE, desired)
        try:
            return _compare(existing, _merge_pyproject(existing, desired))
        except tomllib.TOMLDecodeError:
            return Decision(Outcome.PRESERVE, note="invalid TOML")

    def record(self, existing: str, desired: str) -> str | None:
        return None


POLICIES: dict[PolicyName, Policy] = {
    "managed": Managed(),
    "seed": Seed(),
    "gitignore": GitignoreBlock(),
    "json_merge": JsonMerge(),
    "toml_merge": TomlMerge(),
}
