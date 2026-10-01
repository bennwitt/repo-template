from __future__ import annotations

import json
import os
import re
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from repo_template import __version__
from repo_template.model import ProjectContext, Result, TemplateFile
from repo_template.policies import POLICIES, Outcome
from repo_template.templates import project_files

MANIFEST_NAME = ".repo-template.json"


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
    if spec.legacy_path and not path.exists() and (root / spec.legacy_path).exists():
        result.preserved.append(
            f"{spec.legacy_path} (now {spec.relative_path}: git mv {spec.legacy_path} "
            f"{spec.relative_path}, then move sections that aren't terms into AGENTS.md)"
        )
        return
    existing = path.read_text() if path.exists() else None
    recorded = _recorded_hash(manifest, spec.relative_path)
    policy = "seed" if spec.relative_path in _project_owned(manifest) else spec.policy
    decision = POLICIES[policy].decide(existing, spec.content, recorded)
    if decision.outcome is Outcome.PRESERVE:
        note = f" ({decision.note})" if decision.note else ""
        result.preserved.append(spec.relative_path + note)
        return
    mode_needs_repair = existing is not None and spec.executable and not os.access(path, os.X_OK)
    if decision.outcome is Outcome.UNCHANGED and not mode_needs_repair:
        result.unchanged.append(spec.relative_path)
        return
    bucket = result.created if decision.outcome is Outcome.CREATE else result.updated
    bucket.append(spec.relative_path)
    if not check:
        _write(path, decision.content, spec.executable)


def _project_owned(manifest: dict[str, Any]) -> set[str]:
    """Baseline files the project has taken over; update treats them as seeds."""
    owned = manifest.get("project_owned", [])
    return {item for item in owned if isinstance(item, str)} if isinstance(owned, list) else set()


def skill_packs(root: Path) -> list[str]:
    """The skill packs a repository's manifest lists."""
    packs = _read_manifest(root).get("skill_packs", [])
    return [pack for pack in packs if isinstance(pack, str)] if isinstance(packs, list) else []


def _build_manifest(
    root: Path,
    context: ProjectContext,
    specs: list[TemplateFile],
    packs: Sequence[str] = (),
    owned: Sequence[str] = (),
) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    for spec in specs:
        path = root / spec.relative_path
        if not path.is_file():
            continue
        recorded = POLICIES[spec.policy].record(path.read_text(), spec.content)
        if recorded is not None:
            records[spec.relative_path] = {"policy": spec.policy, "sha256": recorded}
    manifest: dict[str, Any] = {
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
    if packs:
        manifest["skill_packs"] = sorted(set(packs))
    if owned:
        manifest["project_owned"] = sorted(set(owned))
    return manifest


def _write_manifest(root: Path, manifest: dict[str, Any]) -> None:
    content = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    _write(root / MANIFEST_NAME, content, False)


def new_project(
    target: Path,
    *,
    name: str,
    description: str,
    python_version: str,
    packs: Sequence[str] = (),
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
        _apply_file(target, spec, {}, result, check=False)
    _write_manifest(target, _build_manifest(target, context, specs, packs))
    result.created.append(MANIFEST_NAME)
    return result


def update_project(root: Path, *, check: bool = False, add_packs: Sequence[str] = ()) -> Result:
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
        packs = [*skill_packs(root), *add_packs]
        owned = sorted(_project_owned(manifest))
        _write_manifest(root, _build_manifest(root, context, specs, packs, owned))
    return result
