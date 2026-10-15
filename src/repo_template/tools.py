"""Per-machine tools: the CLIs the skills and plugins drive on each machine, each pinned once in
.agents/machine-tools.json, to its newest final release at least a week old (pins.COOLDOWN).

setup-machine.sh installs them from this file (an npm package by version; a GitHub release's
asset only once its SHA-256 matches), and `globals --upstream` reports a newer release past the
cooldown. `below` keeps a tool under a major version the machines can't run yet.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from repo_template.pins import FINAL, Registry, _time, check_pin
from repo_template.upstream import NotFound, Report, clean

TOOLS_NAME = "machine-tools.json"
NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
PLATFORMS = {"darwin-amd64", "darwin-arm64", "linux-amd64", "linux-arm64"}
FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
SHA256 = re.compile(r"[0-9a-f]{64}")
REPOSITORY = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+")


@dataclass(frozen=True)
class Asset:
    file: str
    sha256: str


@dataclass(frozen=True)
class Tool:
    name: str
    registry: str  # npm, or github (a release asset)
    package: str  # the npm package, or owner/repo
    version: str
    published_at: str
    why: str
    below: str | None = None
    tag: str | None = None  # github: the release tag, with {version}
    assets: Mapping[str, Asset] = field(default_factory=dict)  # github: by platform
    pin_exception: str | None = None  # why a release inside its cooldown is pinned


class Releases(Protocol):
    def releases(self, source: str) -> list[dict[str, Any]]:
        """A repository's recent releases as GitHub's API returns them, newest first."""
        ...

    def release(self, source: str, tag: str) -> dict[str, Any] | None:
        """The release with this tag, however old, or None when there is none."""
        ...


def _fail(path: Path, name: str, message: str) -> ValueError:
    return ValueError(f"{path}: tool {name!r}: {message}")


def load_machine_tools(agents_dir: Path) -> dict[str, Tool]:
    """The pinned tools, validated; none when the catalog has no machine-tools.json."""
    path = agents_dir / TOOLS_NAME
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if (
        not isinstance(raw, dict)
        or raw.get("schema") != 1
        or not isinstance(raw.get("tools"), dict)
    ):
        raise ValueError(f"{path}: needs schema 1 and a 'tools' object")
    tools: dict[str, Tool] = {}
    for name, entry in raw["tools"].items():
        if not NAME.fullmatch(name) or not isinstance(entry, dict):
            raise ValueError(f"{path}: {name!r} isn't a tool name (a-z, 0-9, -) with an object")
        registry, package = entry.get("registry"), entry.get("package")
        version, published, why = entry.get("version"), entry.get("publishedAt"), entry.get("why")
        below, tag, assets = entry.get("below"), entry.get("tag"), entry.get("assets", {})
        exception = entry.get("pinException")
        if registry not in ("npm", "github") or not isinstance(package, str) or not package:
            raise _fail(path, name, "needs 'registry' (npm or github) and 'package'")
        if not (isinstance(version, str) and FINAL.fullmatch(version)):
            raise _fail(path, name, "'version' must be a final release, such as 1.2.3")
        if below is not None and not (isinstance(below, str) and FINAL.fullmatch(below)):
            raise _fail(path, name, "'below' must be a version, such as 7")
        if not isinstance(why, str) or not why.strip():
            raise _fail(path, name, "needs a 'why'")
        if exception is not None and not (isinstance(exception, str) and exception.strip()):
            raise _fail(path, name, "a 'pinException' says why, in words")
        try:
            _time(str(published))
        except ValueError:
            raise _fail(path, name, "'publishedAt' must be a time with its zone") from None
        parsed: dict[str, Asset] = {}
        if registry == "github":
            if not REPOSITORY.fullmatch(package):
                raise _fail(path, name, "a github 'package' is owner/repo")
            if not isinstance(tag, str) or "{version}" not in tag:
                raise _fail(path, name, "needs a 'tag' holding {version}")
            if not isinstance(assets, dict) or not assets or set(assets) - PLATFORMS:
                raise _fail(path, name, f"'assets' maps platforms ({', '.join(sorted(PLATFORMS))})")
            for platform, asset in assets.items():
                file = asset.get("file") if isinstance(asset, dict) else None
                digest = asset.get("sha256") if isinstance(asset, dict) else None
                if not (isinstance(file, str) and FILE.fullmatch(file)):
                    raise _fail(path, name, f"{platform}: 'file' must be a plain file name")
                if not (isinstance(digest, str) and SHA256.fullmatch(digest)):
                    raise _fail(path, name, f"{platform}: 'sha256' must be 64 hex digits")
                parsed[platform] = Asset(file, digest)
        elif tag is not None or assets:
            raise _fail(path, name, "only a github tool has a 'tag' and 'assets'")
        tools[name] = Tool(
            name, registry, package, version, str(published), why, below, tag, parsed, exception
        )
    return tools


def github_releases(
    raw: list[dict[str, Any]], tag: str
) -> dict[str, tuple[datetime, dict[str, str]]]:
    """Each final release whose tag fits `tag`: when it was published, and its assets'
    SHA-256 digests by file name (as GitHub records them)."""
    pattern = re.compile(re.escape(tag).replace(re.escape("{version}"), r"(\d+(?:\.\d+)*)"))
    found = {}
    for release in raw:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        matched = pattern.fullmatch(str(release.get("tag_name", "")))
        published = release.get("published_at")
        if not matched or not isinstance(published, str):
            continue
        digests = {}
        for asset in release.get("assets", []):
            digest = asset.get("digest") if isinstance(asset, dict) else None
            if isinstance(digest, str) and digest.startswith("sha256:"):
                digests[str(asset.get("name"))] = digest.removeprefix("sha256:")
        found[matched.group(1)] = (_time(published), digests)
    return found


def check_machine_tools(
    tools: Mapping[str, Tool], registry: Registry, github: Releases, now: datetime, report: Report
) -> None:
    """Each tool's pin into `report`, as check_pins does for MCP servers. A GitHub release's
    asset whose digest differs from the one recorded is for review."""
    for name, tool in sorted(tools.items()):
        label = f"{name}: {tool.registry} {tool.package}"
        move = f"update its version and publishedAt in {TOOLS_NAME}"
        try:
            if tool.registry == "npm":
                releases = registry.releases("npm", tool.package)
            else:
                assert tool.tag is not None
                found = github_releases(github.releases(tool.package), tool.tag)
                if tool.version not in found:  # older than the recent releases listed
                    tag = tool.tag.replace("{version}", tool.version)
                    pinned = github.release(tool.package, tag)
                    found.update(github_releases([pinned] if pinned else [], tool.tag))
                releases = {version: when for version, (when, _) in found.items()}
                move += ", and each asset's sha256 from the release"
                digests = found.get(tool.version, (None, {}))[1]
                for platform, asset in sorted(tool.assets.items()):
                    upstream = digests.get(asset.file)
                    if upstream is not None and upstream != asset.sha256:
                        report.review.append(
                            f"{label}@{tool.version}: {platform} ({asset.file}) has sha256 "
                            f"{clean(upstream)} on GitHub, not the {asset.sha256} {TOOLS_NAME} "
                            f"records"
                        )
        except NotFound:
            report.review.append(f"{label} isn't on {tool.registry} any more")
            continue
        check_pin(
            name,
            label,
            tool.version,
            tool.published_at,
            releases,
            now,
            report,
            record=TOOLS_NAME,
            move=move,
            exception=tool.pin_exception,
            below=tool.below,
        )
