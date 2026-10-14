from __future__ import annotations

import json
import os
import re
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from repo_template import __version__
from repo_template.model import Conflict, ProjectContext, Result, TemplateFile
from repo_template.policies import POLICIES, Outcome, PolicyName, digest
from repo_template.templates import project_files

MANIFEST_NAME = ".repo-template.json"
MERGED_POLICIES = {"json_merge", "toml_merge"}


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


MCP_KEYS = ("mcp_servers", "mcp_kept")  # the pack MCP records: what was written, what was kept
PACKS_ONLY = "packs-only"  # the profile of a repository that takes only skill packs
PERSONAL = "personal"  # skill packs for one person, in a repository that otherwise doesn't change
PERSONAL_NAME = "repo-template.json"  # a personal manifest: in the checkout's .git folder


def _personal_file(root: Path) -> Path | None:
    """Where a personal manifest lives: in the .git folder of a main checkout. A subfolder has
    no .git, and a linked worktree's .git is a file, so neither can have one."""
    git = root / ".git"
    return git / PERSONAL_NAME if git.is_dir() else None


def _linked_personal(root: Path) -> Path | None:
    """The personal manifest of the main checkout, when `root` is a linked worktree of one (its
    .git is a file naming a folder in the main checkout's .git, which holds `commondir`)."""
    git = root / ".git"
    try:
        line = git.read_text().strip() if git.is_file() else ""
    except (OSError, UnicodeDecodeError):
        return None
    if not line.startswith("gitdir:"):
        return None
    folder = (root / line.removeprefix("gitdir:").strip()).resolve()
    try:
        common = (folder / (folder / "commondir").read_text().strip()).resolve()
    except (OSError, UnicodeDecodeError):
        common = folder
    found = common / PERSONAL_NAME
    return found if found.is_file() else None


def _enclosing_personal(root: Path) -> Path | None:
    """The personal manifest of the checkout `root` is a subfolder of, if it has one: run there,
    repo-template couldn't see it and would take the subfolder for a repository of its own."""
    if (root / ".git").exists():
        return None
    for parent in root.parents:
        if (parent / ".git").exists():
            private = _personal_file(parent)
            if private is not None and private.is_file():
                return private
            return _linked_personal(parent)
    return None


def manifest_file(root: Path) -> Path:
    """The repository's manifest: .repo-template.json, else a personal one in .git."""
    private = _personal_file(root)
    if private is not None and private.is_file() and not (root / MANIFEST_NAME).exists():
        return private
    return root / MANIFEST_NAME


def _file_for(root: Path, manifest: Mapping[str, Any]) -> Path:
    """Where `manifest` is written: a personal one in .git, any other in the repository."""
    if manifest.get("profile") != PERSONAL:
        return root / MANIFEST_NAME
    private = _personal_file(root)
    if private is None:  # preflight refuses this first; never write a personal one for everyone
        raise ValueError(f"{root} has no .git folder for a personal manifest")
    return private


def _read_manifest(root: Path) -> dict[str, Any]:
    path = manifest_file(root)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _version_key(version: str) -> tuple[int, int, int]:
    """major.minor.patch, padded: "0.4" and "0.4.0" are the same release."""
    major, minor, patch = (*(int(part) for part in re.findall(r"\d+", version)[:3]), 0, 0, 0)[:3]
    return major, minor, patch


def _refuse_downgrade(root: Path, manifest: dict[str, Any]) -> None:
    """A manifest written by a newer repo-template means this copy of the CLI is out of date."""
    recorded = manifest.get("template_version")
    if isinstance(recorded, str) and _version_key(recorded) > _version_key(__version__):
        raise ValueError(
            f"{manifest_file(root)} was written by repo-template {recorded}, newer than this "
            f"repo-template {__version__}; pull the standards repository (git pull) and run "
            "the command again"
        )


def manifest_version(root: Path) -> str | None:
    """The template version recorded in a repository's manifest, if it has one."""
    value = _read_manifest(root).get("template_version")
    return value if isinstance(value, str) else None


def _infer_context(root: Path) -> ProjectContext:
    project = normalize_project_name(root.name)
    description = ""
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
    description = description or f"{project} project."
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


def _accepted(manifest: dict[str, Any], relative_path: str) -> tuple[str, str] | None:
    """(file hash, baseline hash) of a difference the project accepted, if one is recorded."""
    files = manifest.get("files", {})
    record = files.get(relative_path) if isinstance(files, dict) else None
    accepted = record.get("accepted") if isinstance(record, dict) else None
    if not isinstance(accepted, dict):
        return None
    file_hash, baseline_hash = accepted.get("sha256"), accepted.get("baseline")
    if isinstance(file_hash, str) and isinstance(baseline_hash, str):
        return file_hash, baseline_hash
    return None


def _reported(result: Result, relative_path: str) -> bool:
    """Whether a file is already listed for review, so each file is reported once."""
    return any(
        item == relative_path or item.startswith(f"{relative_path} (") for item in result.preserved
    )


def _apply_file(
    root: Path,
    spec: TemplateFile,
    manifest: dict[str, Any],
    result: Result,
    *,
    check: bool,
    baseline: dict[str, TemplateFile],
) -> None:
    path = root / spec.relative_path
    if _reported(result, spec.relative_path):
        return
    owned = spec.relative_path in _project_owned(manifest)
    legacy = root / spec.legacy_path if spec.legacy_path else None
    legacy_spec = baseline.get(str(spec.legacy_path)) if spec.legacy_path else None
    if (
        legacy is not None
        and not owned  # a project that took the file over decides about its old name too
        and not path.exists()
        and legacy.is_file()
        and legacy.read_text() != (legacy_spec.content if legacy_spec else None)
    ):
        result.preserved.append(
            f"{spec.legacy_path} (now {spec.relative_path}: {spec.legacy_hint})"
        )
        result.conflicts.append(
            Conflict(
                path=str(spec.legacy_path),
                existing=legacy.read_text(),
                desired="",
                reason=spec.legacy_hint,
                moves_to=spec.relative_path,
                legacy_baseline=legacy_spec.content if legacy_spec else None,
                legacy_policy=legacy_spec.policy if legacy_spec else "managed",
            )
        )
        return
    existing = path.read_text() if path.exists() else None
    if owned and existing is None:
        # The project took the file over and then deleted it: that is its decision too.
        result.unchanged.append(spec.relative_path)
        return
    recorded = _recorded_hash(manifest, spec.relative_path)
    policy = "seed" if owned else spec.policy
    decision = POLICIES[policy].decide(existing, spec.content, recorded)
    if decision.outcome is Outcome.PRESERVE and existing is not None:
        if _accepted(manifest, spec.relative_path) == (digest(existing), digest(spec.content)):
            result.unchanged.append(spec.relative_path)
            return
        note = f" ({decision.note})" if decision.note else ""
        result.preserved.append(spec.relative_path + note)
        result.conflicts.append(
            Conflict(
                path=spec.relative_path,
                existing=existing,
                desired=spec.content,
                reason=decision.note,
                executable=spec.executable,
                # A merged file is preserved only when it can't be merged; the baseline's version
                # of it is a bare template that would replace the project's metadata.
                replaceable=policy not in MERGED_POLICIES,
                policy=spec.policy,
            )
        )
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
    previous: dict[str, Any] | None = None,
    mcp: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    for spec in specs:
        path = root / spec.relative_path
        if not path.is_file():
            continue
        current = path.read_text()
        record: dict[str, Any] = {}
        recorded = POLICIES[spec.policy].record(current, spec.content)
        if recorded is not None:
            record = {"policy": spec.policy, "sha256": recorded}
        state = (digest(current), digest(spec.content))
        if previous and _accepted(previous, spec.relative_path) == state:
            record.update(policy=spec.policy, accepted={"sha256": state[0], "baseline": state[1]})
        if record:
            records[spec.relative_path] = record
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
    for key in MCP_KEYS:
        if mcp and mcp.get(key):
            manifest[key] = dict(sorted(mcp[key].items()))
    return manifest


def write_file(root: Path, relative_path: str, content: str, *, executable: bool = False) -> None:
    """Write a repository file atomically."""
    _write(root / relative_path, content, executable)


def accept_difference(
    root: Path, relative_path: str, existing: str, desired: str, policy: PolicyName = "managed"
) -> None:
    """Record that the project keeps `existing` while the baseline's version is `desired`.

    update stops reporting the file until either side changes. The record has the shape
    update itself writes, so a resolved file leaves nothing for the next update to do.
    """
    manifest = _read_manifest(root)
    files = manifest.setdefault("files", {})
    files[relative_path] = {
        "policy": policy,
        "accepted": {"sha256": digest(existing), "baseline": digest(desired)},
    }
    _write_manifest(root, manifest)


def record_baseline(root: Path, relative_path: str, content: str, policy: PolicyName) -> None:
    """Record a file that now holds the baseline's `content`, as update would."""
    manifest = _read_manifest(root)
    files = manifest.setdefault("files", {})
    recorded = POLICIES[policy].record(content, content)
    if recorded is None:
        files.pop(relative_path, None)
    else:
        files[relative_path] = {"policy": policy, "sha256": recorded}
    _write_manifest(root, manifest)


def own_file(root: Path, relative_path: str) -> None:
    """Add a file to project_owned: update leaves it alone from now on."""
    manifest = _read_manifest(root)
    manifest["project_owned"] = sorted(_project_owned(manifest) | {relative_path})
    files = manifest.get("files")
    if isinstance(files, dict):
        files.pop(relative_path, None)  # it differs from the baseline, so update keeps no hash
    _write_manifest(root, manifest)


def _write_manifest(root: Path, manifest: dict[str, Any]) -> None:
    content = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    _write(_file_for(root, manifest), content, False)


def new_project(
    target: Path,
    *,
    name: str,
    description: str,
    python_version: str,
    packs: Sequence[str] = (),
    mcp: Mapping[str, Mapping[str, str]] | None = None,
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
        _apply_file(target, spec, {}, result, check=False, baseline={})
    _write_manifest(target, _build_manifest(target, context, specs, packs, mcp=mcp))
    result.created.append(MANIFEST_NAME)
    return result


def _uses_package_layout(root: Path, context: ProjectContext) -> bool:
    """False when the code already lives in src/ but not in src/<package>/: a flat layout."""
    src = root / "src"
    return not src.is_dir() or (src / context.package_name).is_dir()


def read_manifest(root: Path) -> dict[str, Any]:
    """The repository's manifest (.repo-template.json, or a personal one in .git), or {} when it
    has none."""
    return _read_manifest(root.resolve())


def _finish_manifest(
    root: Path, manifest: dict[str, Any], proposed: dict[str, Any], result: Result, *, check: bool
) -> Result:
    path = _file_for(root, proposed)
    label = path.relative_to(root).as_posix()
    if proposed == manifest:
        result.unchanged.append(label)
        return result
    # In check mode the records come from the files as they are now. When no file changes,
    # that is exactly what update would write, so a clean check still means nothing to do.
    (result.updated if path.exists() else result.created).append(label)
    if not check:
        _write_manifest(root, proposed)
    return result


def _carried(
    manifest: dict[str, Any], mcp: Mapping[str, Mapping[str, str]] | None
) -> Mapping[str, Mapping[str, str]]:
    """The pack MCP records to write: `mcp`, or the manifest's carried forward."""
    if mcp is not None:
        return mcp
    return {key: manifest[key] for key in MCP_KEYS if isinstance(manifest.get(key), dict)}


PROFILES = ("python-uv", PACKS_ONLY, PERSONAL)


def preflight(
    root: Path, *, packs_only: bool, add_packs: Sequence[str], personal: bool = False
) -> dict[str, Any]:
    """Every reason `update` (or `check`) can't run, checked before anything is written; the
    manifest, read once. A packs-only or personal manifest makes the run one too."""
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"repository directory does not exist: {root}")
    shared, private = root / MANIFEST_NAME, _personal_file(root)
    linked = _linked_personal(root)
    if linked is not None:  # it can't see the record, so it would take this for a new repository
        raise ValueError(
            f"{root} is a linked worktree of a checkout adopted personally ({linked}); run "
            f"repo-template in that checkout"
        )
    enclosing = _enclosing_personal(root)
    if enclosing is not None and not shared.exists():  # a sub-project with a manifest is its own
        raise ValueError(
            f"{root} is inside a checkout adopted personally ({enclosing}); run repo-template "
            f"at that checkout's top folder"
        )
    if shared.exists() and private is not None and private.is_file():
        raise ValueError(
            f"{shared} adopts this repository for everyone, so your personal adoption has to go: "
            f"move {MANIFEST_NAME} aside, set skill_packs to [] in {private} and run "
            f"`repo-template update {root}` (it removes the links, the exclude block, the Codex "
            f"block and your local-scope servers), then delete {private} and put "
            f"{MANIFEST_NAME} back"
        )
    if personal and packs_only:
        raise ValueError("--personal and --packs-only adopt a repository differently; choose one")
    manifest = _read_manifest(root)
    found = manifest_file(root)
    profile = manifest.get("profile")
    if manifest and profile not in PROFILES:
        raise ValueError(
            f"{found} isn't a repo-template manifest (no known profile); "
            f"repo-template won't overwrite it, so move it aside first"
        )
    if found == shared and profile == PERSONAL:
        raise ValueError(
            f"{shared} says it is personal, but a personal manifest lives in .git, where no one "
            f"else sees it; move it aside first"
        )
    if personal and private is None:
        raise ValueError(
            f"--personal needs the top folder of a Git checkout: {root} has no .git folder (a "
            f"subfolder has none; a linked worktree's or a submodule's is a file)"
        )
    if personal and shared.exists():
        raise ValueError(
            f"{shared} adopts this repository for everyone; personal adoption is for a "
            f"repository you don't manage, so update it without --personal"
        )
    if packs_only and profile == "python-uv":
        raise ValueError(f"{shared} has the Python/uv baseline; update it without --packs-only")
    if packs_only and profile == PERSONAL:
        raise ValueError(f"{found} adopts this repository for you alone; drop --packs-only")
    if (packs_only or personal) and not manifest and not add_packs:
        flag = "--personal" if personal else "--packs-only"
        raise ValueError(f"{flag} adopts a repository for its skill packs; name one with --pack")
    _refuse_downgrade(root, manifest)
    return manifest


def update_packs_only(
    root: Path,
    *,
    check: bool = False,
    add_packs: Sequence[str] = (),
    mcp: Mapping[str, Mapping[str, str]] | None = None,
    profile: str = PACKS_ONLY,
) -> Result:
    """A repository that takes only skill packs, and their MCP servers, from repo-template: its
    manifest records those and nothing else, and no baseline file is written. `profile`
    PERSONAL keeps the manifest in .git."""
    root = root.resolve()
    manifest = preflight(
        root,
        packs_only=profile == PACKS_ONLY,
        personal=profile == PERSONAL,
        add_packs=add_packs,
    )
    proposed: dict[str, Any] = {
        "schema": 1,
        "template_version": __version__,
        "profile": profile,
    }
    packs = sorted({*skill_packs(root), *add_packs})
    if packs:
        proposed["skill_packs"] = packs
    owned = sorted(_project_owned(manifest))
    if owned:
        proposed["project_owned"] = owned
    records = _carried(manifest, mcp)
    for key in MCP_KEYS:
        if records.get(key):
            proposed[key] = dict(sorted(records[key].items()))
    return _finish_manifest(root, manifest, proposed, Result(root), check=check)


def update_project(
    root: Path,
    *,
    check: bool = False,
    add_packs: Sequence[str] = (),
    mcp: Mapping[str, Mapping[str, str]] | None = None,
) -> Result:
    """`mcp` holds the pack MCP records to keep (mcp_servers, mcp_kept); None carries the
    manifest's forward."""
    root = root.resolve()
    manifest = preflight(root, packs_only=False, add_packs=add_packs)
    if manifest.get("profile") in (PACKS_ONLY, PERSONAL):
        raise ValueError(
            f"{manifest_file(root)} takes only skill packs; to take the Python/uv baseline, "
            f"delete it and run update"
        )
    context = _context_from_manifest(root, manifest)
    specs = project_files(context, package=_uses_package_layout(root, context))
    baseline = {spec.relative_path: spec for spec in specs}
    result = Result(root)
    for spec in specs:
        _apply_file(root, spec, manifest, result, check=check, baseline=baseline)
    packs = [*skill_packs(root), *add_packs]
    owned = sorted(_project_owned(manifest))
    proposed = _build_manifest(
        root, context, specs, packs, owned, manifest, _carried(manifest, mcp)
    )
    return _finish_manifest(root, manifest, proposed, result, check=check)
