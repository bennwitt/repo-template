"""Freshness evidence for the existing updater, separate from installed provenance.

The cache is disposable: missing/corrupt evidence forces inspection, never installation.
No cache record grants permission to apply an upstream change.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import tomllib
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from repo_template.release_policy import FRESHNESS


def stamp(now: datetime) -> str:
    return now.astimezone(UTC).isoformat().replace("+00:00", "Z")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def cache_path(root: Path) -> Path:
    base = Path(os.environ.get("REPO_TEMPLATE_CACHE", Path.home() / ".cache/repo-template"))
    return base / "upstream" / (fingerprint(str(root.resolve())) + ".json")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".maintenance-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class CheckCache:
    def __init__(
        self,
        root: Path,
        *,
        now: datetime | None = None,
        max_age_hours: float = 24,
        force: bool = False,
        dry_run: bool = False,
        path: Path | None = None,
    ) -> None:
        if not math.isfinite(max_age_hours) or max_age_hours <= 0:
            raise ValueError("--max-age-hours must be a finite positive number")
        self.path = path or cache_path(root)
        self.catalog_fingerprint = fingerprint(inventory(root))
        self.now = now or datetime.now(UTC)
        self.max_age = timedelta(hours=max_age_hours)
        self.force, self.dry_run = force, dry_run
        raw = read_json(self.path)
        self.records: dict[str, Any] = raw.get("sources", {}) if raw.get("schema") == 1 else {}
        if not isinstance(self.records, dict):
            self.records = {}
        self.observed: dict[str, dict[str, Any]] = {}

    def inspect(
        self, identity: str, configuration: Any, inspect: Callable[[], dict[str, Any]]
    ) -> dict[str, Any]:
        digest = fingerprint(configuration)
        previous = self.records.get(identity, {})
        if not isinstance(previous, dict):
            previous = {}
        matches = previous.get("fingerprint") == digest
        record = dict(previous) if matches else {"fingerprint": digest}
        fresh = False
        try:
            checked = datetime.fromisoformat(record["last_successful_check_at"])
            fresh = timedelta(0) <= self.now - checked < self.max_age
        except (KeyError, TypeError, ValueError):
            pass
        if fresh and not self.force and not record.get("failure_reason"):
            payload = record.get("result")
            if isinstance(payload, dict):
                self.observed[identity] = {**record, "cached": True}
                return payload
        record["last_checked_at"] = stamp(self.now)
        try:
            result = inspect()
        except Exception as exc:
            record.update(sync_status="check_failed", failure_reason=str(exc))
            self._save(identity, record)
            raise
        record.update(
            last_successful_check_at=stamp(self.now),
            failure_reason=None,
            result=result,
            sync_status="checked",
        )
        self._save(identity, record)
        return result

    def _save(self, identity: str, record: dict[str, Any]) -> None:
        self.records[identity] = record
        self.observed[identity] = {**record, "cached": False}
        if not self.dry_run:
            # Preserve evidence written for other sources by a concurrent inspection.
            latest = read_json(self.path)
            records = latest.get("sources", {}) if latest.get("schema") == 1 else {}
            if not isinstance(records, dict):
                records = {}
            records[identity] = record
            atomic_json(
                self.path,
                {**latest, "schema": 1, "sources": records},
            )

    def complete(self) -> None:
        """Record coverage only after an unfiltered inspection finishes."""
        if not self.dry_run:
            latest = read_json(self.path)
            latest.update(
                catalog_fingerprint=self.catalog_fingerprint, coverage=sorted(self.observed)
            )
            atomic_json(self.path, latest)


def freshness_warning(root: Path, *, now: datetime | None = None) -> str | None:
    """Offline advisory only; it never changes a repository's reconciliation status."""
    now = now or datetime.now(UTC)
    raw = read_json(cache_path(root))
    try:
        current = fingerprint(inventory(root))
    except (OSError, ValueError, TypeError):
        return "Upstream freshness is unknown: local inventory could not be read."
    if raw.get("catalog_fingerprint") != current:
        return "Upstream freshness is unknown for this catalog revision; using local assets."
    records = raw.get("sources", {})
    coverage = raw.get("coverage")
    if not isinstance(records, dict) or not isinstance(coverage, list) or not coverage:
        return "Upstream freshness is unknown; using the validated local catalog."
    for identity in coverage:
        try:
            record = records[identity]
            age = now - datetime.fromisoformat(record["last_successful_check_at"])
            if record.get("failure_reason") or not timedelta(0) <= age < FRESHNESS:
                raise ValueError("stale")
        except (KeyError, TypeError, ValueError):
            return "Upstream checks are stale or failed; using the validated local catalog."
    return None


class CachedGitHub:
    """Cache immutable reference resolution and release metadata, never file downloads."""

    def __init__(self, github: Any, cache: CheckCache, configuration: Any) -> None:
        self.github, self.cache, self.configuration = github, cache, configuration

    def __getattr__(self, name: str) -> Any:
        return getattr(self.github, name)

    def blob(self, source: str, sha: str) -> bytes:
        from repo_template.catalog import blob_sha

        if not re.fullmatch(r"[a-f0-9]{40}", sha):
            raise ValueError("blob reference must be an immutable Git hash")
        path = self.cache.path.parent / "objects" / sha
        try:
            data = path.read_bytes()
            if blob_sha(data) == sha:
                return data
        except OSError:
            pass
        data = cast(bytes, self.github.blob(source, sha))
        if blob_sha(data) != sha:
            raise ValueError("downloaded blob does not match its immutable reference")
        if not self.cache.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".blob-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        return data

    def commit(self, source: str, ref: str) -> tuple[str, str]:
        result = self.cache.inspect(
            f"github-ref:{source}#{ref}",
            self.configuration,
            lambda: {"commit": list(self.github.commit(source, ref))},
        )
        return result["commit"][0], result["commit"][1]

    def releases(self, source: str) -> list[dict[str, Any]]:
        result = self.cache.inspect(
            f"github-releases:{source}",
            self.configuration,
            lambda: {"releases": self.github.releases(source)},
        )
        return cast(list[dict[str, Any]], result["releases"])

    def release(self, source: str, tag: str) -> dict[str, Any] | None:
        result = self.cache.inspect(
            f"github-release:{source}#{tag}",
            self.configuration,
            lambda: {"release": self.github.release(source, tag)},
        )
        return cast(dict[str, Any] | None, result["release"])


def inventory(root: Path) -> list[dict[str, Any]]:
    """Derive inventory from authoritative manifests, including disabled/excluded assets."""
    agents = root / ".agents"
    sources = read_json(agents / "skill-sources.json")
    lock = read_json(agents / ".skill-lock.json").get("skills", {})
    rows: list[dict[str, Any]] = []
    for name, record in sorted(lock.items()):
        provenance = sources.get("skills", {}).get(name, {})
        rows.append(
            dict(
                name=name,
                type="skill",
                origin="vendored",
                source=record.get("source"),
                installed_ref=provenance.get("commit"),
                provenance=provenance,
                clients=["codex", "claude"],
            )
        )
    for name, record in sorted(sources.get("local", {}).items()):
        rows.append(
            dict(
                name=name,
                type="skill",
                origin="local",
                provenance=record,
                clients=["codex", "claude"],
            )
        )
    for name, record in sorted(sources.get("sources", {}).items()):
        rows.append(
            dict(
                name=name,
                type="source",
                origin="upstream",
                configuration=record,
                exclusions=sources.get("ignored", {}).get(name, {}),
            )
        )
    for filename, section, kind in (
        ("skill-packs.json", None, "pack"),
        ("mcp-servers.json", "servers", "mcp"),
        ("mcp-development.json", "packages", "development"),
        ("machine-tools.json", "tools", "machine-tool"),
    ):
        document = read_json(agents / filename)
        entries = document.get(section, {}) if section else document
        for name, record in sorted(entries.items()):
            rows.append(dict(name=name, type=kind, configuration=record))
    settings = read_json(agents / "claude-settings.json")
    for name, enabled in sorted(settings.get("portable", {}).get("enabledPlugins", {}).items()):
        rows.append(dict(name=name, type="plugin", client="claude", enabled=enabled))
    for name, record in sorted(sources.get("plugins", {}).items()):
        rows.append(dict(name=name, type="plugin-provider", configuration=record))
    for name, record in sorted(sources.get("references", {}).items()):
        rows.append(dict(name=name, type="reference", configuration=record))
    rows.extend(dependencies(root))
    return rows


def dependencies(root: Path) -> list[dict[str, Any]]:
    """Direct development/example requirements with installed versions from existing locks."""
    rows = []
    projects = [
        root,
        *(root / "examples/mcp" / n for n in ("python", "langchain", "legacy-langchain")),
    ]
    for project in projects:
        if not (project / "pyproject.toml").is_file():
            continue
        raw = tomllib.loads((project / "pyproject.toml").read_text())
        lock = (
            tomllib.loads((project / "uv.lock").read_text())
            if (project / "uv.lock").is_file()
            else {}
        )
        locked = {p["name"]: p["version"] for p in lock.get("package", [])}
        specs = list(raw.get("project", {}).get("dependencies", []))
        specs.extend(raw.get("build-system", {}).get("requires", []))
        for group in raw.get("dependency-groups", {}).values():
            specs.extend(s for s in group if isinstance(s, str))
        for spec in sorted(set(specs)):
            match = re.match(r"[A-Za-z0-9_.-]+", spec)
            if match:
                name = re.sub(r"[-_.]+", "-", match[0]).lower()
                rows.append(
                    dict(
                        name=name,
                        type="dependency",
                        configuration=dict(
                            registry="pypi",
                            package=name,
                            version=locked.get(name),
                            requirement=spec,
                            manifest=str(project.relative_to(root) / "pyproject.toml"),
                        ),
                    )
                )
    project = root / "examples/mcp/typescript"
    package = read_json(project / "package.json")
    lock = read_json(project / "package-lock.json").get("packages", {})
    for name, spec in sorted(
        (package.get("dependencies", {}) | package.get("devDependencies", {})).items()
    ):
        rows.append(
            dict(
                name=name,
                type="dependency",
                configuration=dict(
                    registry="npm",
                    package=name,
                    version=lock.get("node_modules/" + name, {}).get("version"),
                    requirement=spec,
                    manifest="examples/mcp/typescript/package.json",
                ),
            )
        )
    return rows


def check_dependencies(root: Path, registry: Any, now: datetime, report: Any) -> None:
    from repo_template.pins import FINAL, check_pin
    from repo_template.upstream import NetworkError, NotFound

    for row in dependencies(root):
        config = row["configuration"]
        name, version, source = row["name"], config["version"], config["registry"]
        label = f"{config['manifest']}: {name}"
        try:
            releases = registry.releases(source, name)
        except NotFound:
            report.review.append(f"{label}: dependency unavailable; review its lock")
            continue
        except NetworkError as exc:
            report.errors.append(f"{label}: {exc}")
            continue
        if not isinstance(version, str) or not FINAL.fullmatch(version) or version not in releases:
            report.review.append(
                f"{label}: unresolved, preview or unavailable version {version}; review required"
            )
            continue
        check_pin(
            label,
            label,
            version,
            stamp(releases[version]),
            releases,
            now,
            report,
            record=config["manifest"],
            move="review constraints and regenerate this environment's lock",
        )


def automatic_reason(
    source: str, sources: Mapping[str, Any], *, adding: bool, changed: list[str], notes: list[str]
) -> str | None:
    """A successful scan alone is insufficient authority for unattended execution changes."""
    record = sources.get("sources", {}).get(source)
    if not isinstance(record, dict):
        return "new source requires review"
    if record.get("admission", {}).get("updates", "auto") != "auto":
        return "source policy requires review"
    if adding:
        return "new capability requires reviewed placement"
    if any(Path(path).suffix.lower() not in {".md", ".txt", ".rst"} for path in changed):
        return "executable or non-documentation changes require review"
    if notes:
        return notes[0]
    return None


class CachedRegistry:
    """Cache package inspection while leaving version selection in the existing pin checker."""

    def __init__(self, registry: Any, cache: CheckCache, configuration: Any) -> None:
        self.registry, self.cache, self.configuration = registry, cache, configuration

    def releases(self, registry: str, package: str) -> dict[str, datetime]:
        result = self.cache.inspect(
            f"{registry}:{package}",
            self.configuration,
            lambda: {
                "releases": {
                    v: stamp(t) for v, t in self.registry.releases(registry, package).items()
                }
            },
        )
        return {v: datetime.fromisoformat(t) for v, t in result["releases"].items()}


def inspect_reference(record: dict[str, Any], github: Any) -> dict[str, Any]:
    if record.get("kind") == "github":
        commit, tree = github.commit(record["source"], record.get("ref", "HEAD"))
        return {"available_ref": commit, "tree": tree}
    url = record.get("url", "")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("documentation references need an HTTPS URL")
    request = urllib.request.Request(url, headers={"User-Agent": "repo-template"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("documentation reference exceeds 2 MiB")
    return {"available_ref": hashlib.sha256(data).hexdigest(), "url": url}
