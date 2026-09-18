from __future__ import annotations

import hashlib
import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any

from repo_template import __version__
from repo_template.model import ProjectContext, Result, TemplateFile
from repo_template.templates import project_files

MANIFEST_NAME = ".repo-template.json"
GITIGNORE_START = "# >>> repo-template managed defaults"
GITIGNORE_END = "# <<< repo-template managed defaults"


def normalize_project_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        raise ValueError("repository name must contain at least one letter or number")
    return normalized


def package_name(project_name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", project_name).strip("_").lower()
    if normalized and normalized[0].isdigit():
        normalized = "project_" + normalized
    return normalized


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _read_manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _infer_context(root: Path) -> ProjectContext:
    project = normalize_project_name(root.name)
    description = f"{project} project."
    python_version = "3.12"
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text())
            metadata = data.get("project", {})
            if isinstance(metadata, dict):
                raw_name = metadata.get("name")
                raw_description = metadata.get("description")
                raw_python = metadata.get("requires-python")
                if isinstance(raw_name, str):
                    project = normalize_project_name(raw_name)
                if isinstance(raw_description, str):
                    description = raw_description
                if isinstance(raw_python, str):
                    match = re.search(r"(\d+\.\d+)", raw_python)
                    if match:
                        python_version = match.group(1)
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return ProjectContext(project, package_name(project), description, python_version)


def _context_from_manifest(root: Path, manifest: dict[str, Any]) -> ProjectContext:
    raw = manifest.get("project")
    if not isinstance(raw, dict):
        return _infer_context(root)
    inferred = _infer_context(root)
    return ProjectContext(
        project_name=str(raw.get("name", inferred.project_name)),
        package_name=str(raw.get("package", inferred.package_name)),
        description=str(raw.get("description", inferred.description)),
        python_version=str(raw.get("python", inferred.python_version)),
    )


def _write(path: Path, content: str, executable: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.repo-template-tmp")
    temporary.write_text(content)
    temporary.replace(path)
    if executable:
        path.chmod(path.stat().st_mode | 0o111)


def _merge_gitignore(existing: str, desired: str) -> str:
    managed = f"{GITIGNORE_START}\n{desired.rstrip()}\n{GITIGNORE_END}\n"
    pattern = re.compile(
        re.escape(GITIGNORE_START) + r".*?" + re.escape(GITIGNORE_END) + r"\n?",
        re.DOTALL,
    )
    if pattern.search(existing):
        return pattern.sub(managed, existing)
    prefix = existing.rstrip()
    return f"{prefix}\n\n{managed}" if prefix else managed


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
    for table in ("tool.pytest.ini_options", "tool.ruff", "tool.ruff.lint", "tool.mypy"):
        if _table_block(proposed, table) is not None:
            continue
        block = _table_block(desired, table)
        if block:
            proposed = proposed.rstrip() + "\n\n" + block + "\n"
    tomllib.loads(proposed)
    return proposed


def _recorded_hash(manifest: dict[str, Any], relative_path: str) -> str | None:
    files = manifest.get("files", {})
    if not isinstance(files, dict):
        return None
    record = files.get(relative_path)
    if not isinstance(record, dict):
        return None
    value = record.get("sha256")
    return value if isinstance(value, str) else None


def _apply_file(
    root: Path,
    spec: TemplateFile,
    manifest: dict[str, Any],
    result: Result,
    *,
    check: bool,
) -> None:
    path = root / spec.relative_path
    if not path.exists():
        result.created.append(spec.relative_path)
        if not check:
            _write(path, spec.content, spec.executable)
        return

    existing = path.read_text()
    proposed = spec.content
    if spec.policy == "seed":
        result.unchanged.append(spec.relative_path)
        return
    if spec.policy == "gitignore":
        proposed = _merge_gitignore(existing, spec.content)
    elif spec.policy == "json_merge":
        try:
            proposed = _merge_json(existing, spec.content)
        except json.JSONDecodeError:
            result.preserved.append(f"{spec.relative_path} (invalid JSON)")
            return
    elif spec.policy == "toml_merge":
        try:
            proposed = _merge_pyproject(existing, spec.content)
        except tomllib.TOMLDecodeError:
            result.preserved.append(f"{spec.relative_path} (invalid TOML)")
            return

    mode_needs_update = spec.executable and not os.access(path, os.X_OK)
    if existing == proposed and not mode_needs_update:
        result.unchanged.append(spec.relative_path)
        return

    if spec.policy in {"gitignore", "json_merge", "toml_merge"}:
        result.updated.append(spec.relative_path)
        if not check:
            _write(path, proposed, spec.executable)
        return

    recorded = _recorded_hash(manifest, spec.relative_path)
    if _digest(existing) == _digest(spec.content) or recorded == _digest(existing):
        result.updated.append(spec.relative_path)
        if not check:
            _write(path, proposed, spec.executable)
        return
    result.preserved.append(spec.relative_path)


def _build_manifest(
    root: Path, context: ProjectContext, specs: list[TemplateFile]
) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    for spec in specs:
        path = root / spec.relative_path
        if not path.is_file():
            continue
        current = path.read_text()
        if spec.policy == "seed" and current != spec.content:
            continue
        if spec.policy == "managed" and current != spec.content:
            continue
        records[spec.relative_path] = {
            "policy": spec.policy,
            "sha256": _digest(current),
        }
    return {
        "schema": 1,
        "template_version": __version__,
        "profile": "python-uv",
        "project": {
            "name": context.project_name,
            "package": context.package_name,
            "description": context.description,
            "python": context.python_version,
        },
        "files": records,
    }


def _write_manifest(root: Path, manifest: dict[str, Any]) -> None:
    content = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    _write(root / MANIFEST_NAME, content, False)


def new_project(
    target: Path,
    *,
    name: str,
    description: str,
    python_version: str,
) -> Result:
    target = target.resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError(f"target directory is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    project = normalize_project_name(name)
    context = ProjectContext(project, package_name(project), description, python_version)
    specs = project_files(context)
    result = Result(target)
    for spec in specs:
        content = spec.content
        if spec.policy == "gitignore":
            content = _merge_gitignore("", content)
        elif spec.policy == "json_merge":
            content = json.dumps(json.loads(content), indent=2, ensure_ascii=False) + "\n"
        _write(target / spec.relative_path, content, spec.executable)
        result.created.append(spec.relative_path)
    _write_manifest(target, _build_manifest(target, context, specs))
    result.created.append(MANIFEST_NAME)
    return result


def update_project(root: Path, *, check: bool = False) -> Result:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"repository directory does not exist: {root}")
    manifest = _read_manifest(root)
    context = _context_from_manifest(root, manifest)
    specs = project_files(context)
    result = Result(root)
    for spec in specs:
        _apply_file(root, spec, manifest, result, check=check)
    if not check:
        _write_manifest(root, _build_manifest(root, context, specs))
    return result
