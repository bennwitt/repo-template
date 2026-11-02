"""Validated MCP development pins: documentation/test inputs, never app dependencies."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from repo_template.mcp import Pin, _pin
from repo_template.pins import FINAL, Registry, check_pin
from repo_template.upstream import NotFound, Report

DEVELOPMENT_NAME = "mcp-development.json"


def load_development(agents: Path) -> dict[str, Pin]:
    """Read optional development metadata; reject malformed inputs before any network use."""
    path = agents / DEVELOPMENT_NAME
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if (
        not isinstance(raw, dict)
        or raw.get("schema") != 1
        or not isinstance(raw.get("packages"), dict)
        or not raw["packages"]
    ):
        raise ValueError(f"{path}: needs schema 1 and nonempty packages")
    try:
        revision = raw["protocol"]
        if not isinstance(revision, str) or date.fromisoformat(revision).isoformat() != revision:
            raise ValueError
    except (KeyError, ValueError):
        raise ValueError(f"{path}: protocol must be a YYYY-MM-DD revision") from None
    result = {}
    for name, value in raw["packages"].items():
        pin = _pin(path, name, value)
        if pin is None or not FINAL.fullmatch(pin.version):
            raise ValueError(f"{path}: {name}: needs an exact final release")
        result[name] = pin
    return result


def check_development(agents: Path, registry: Registry, now: datetime, report: Report) -> None:
    """Report newer development releases; maintainers update fixtures before accepting them."""
    for name, pin in sorted(load_development(agents).items()):
        label = f"mcp-dev:{name}: {pin.registry} {pin.package}"
        try:
            releases = registry.releases(pin.registry, pin.package)
        except NotFound:
            report.review.append(f"{label} isn't on {pin.registry} any more")
            continue
        check_pin(
            f"mcp-dev:{name}",
            label,
            pin.version,
            pin.published_at,
            releases,
            now,
            report,
            record=DEVELOPMENT_NAME,
            move=(
                "review the MCP development baseline, update fixture locks "
                "and run compatibility tests"
            ),
            exception=pin.exception,
        )
