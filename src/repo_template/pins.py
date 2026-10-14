"""Newer releases of the packages MCP servers pin, for `globals --upstream`.

A release is offered once it is a week old (COOLDOWN), so a bad release has time to be caught
and pulled first; pre-releases, and releases yanked or deprecated, never are. A pin younger than
that needs a `pinException` saying why, and is reported once the exception is no longer needed.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, Protocol

from repo_template.mcp import MCP_SERVERS_NAME, Server
from repo_template.upstream import NetworkError, NotFound, Report, clean

COOLDOWN = timedelta(days=7)
FINAL = re.compile(r"\d+(?:\.\d+)*")  # 1.2.3: a final release, the only kind offered
URLS = {"npm": "https://registry.npmjs.org/{}", "pypi": "https://pypi.org/pypi/{}/json"}


class Registry(Protocol):
    def releases(self, registry: str, package: str) -> dict[str, datetime]:
        """Each final release of `package` that wasn't yanked or deprecated, and when it was
        published. Raises NotFound for an unknown package, NetworkError otherwise."""
        ...


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def npm_releases(document: Any) -> dict[str, datetime]:
    times, versions = document.get("time", {}), document.get("versions", {})
    return {
        version: _time(times[version])
        for version, meta in versions.items()
        if FINAL.fullmatch(version)
        and isinstance(meta, dict)
        and not meta.get("deprecated")
        and isinstance(times.get(version), str)
    }


def pypi_releases(document: Any) -> dict[str, datetime]:
    found = {}
    for version, files in document.get("releases", {}).items():
        live = [
            item["upload_time_iso_8601"]
            for item in files
            if isinstance(item, dict)
            and not item.get("yanked")
            and isinstance(item.get("upload_time_iso_8601"), str)
        ]
        if FINAL.fullmatch(version) and live:
            found[version] = min(_time(when) for when in live)
    return found


class HttpRegistry:
    """npm's and PyPI's public JSON APIs; no login."""

    def releases(self, registry: str, package: str) -> dict[str, datetime]:
        url = URLS[registry].format(urllib.parse.quote(package, safe="@"))
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                document = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            error = NotFound if exc.code == 404 else NetworkError
            raise error(f"GET {url}: HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise NetworkError(f"GET {url}: {clean(str(exc))}") from None
        return (npm_releases if registry == "npm" else pypi_releases)(document)


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _day(when: datetime) -> str:
    return when.strftime("%Y-%m-%d")


def check_pins(
    servers: Mapping[str, Server], registry: Registry, now: datetime, report: Report
) -> None:
    """Add each pin's state to `report`: a newer release past its cooldown is a change; a pin
    that is gone, recorded wrongly or younger than the cooldown without a reason is for review."""
    for name, server in sorted(servers.items()):
        pin = server.pin
        if pin is None:
            continue
        label = f"{name}: {pin.registry} {pin.package}"
        if not FINAL.fullmatch(pin.version):
            report.review.append(f"{label}@{pin.version} isn't a final release; pin one")
            continue
        try:
            releases = registry.releases(pin.registry, pin.package)
        except NotFound:
            report.review.append(f"{label} isn't on {pin.registry} any more")
            continue
        published = releases.get(pin.version)
        if published is None:
            report.review.append(
                f"{label}@{pin.version} was yanked or deprecated, or never published; pin "
                f"another release"
            )
        elif abs(published - _time(pin.published_at)) > timedelta(minutes=1):
            report.review.append(
                f"{label}@{pin.version} was published {published:%Y-%m-%dT%H:%M:%SZ}, not "
                f"{pin.published_at} as {MCP_SERVERS_NAME} records"
            )
        elif now - published < COOLDOWN and not pin.exception:
            report.review.append(
                f"{label}@{pin.version} is inside its cooldown until "
                f"{_day(published + COOLDOWN)}; pin an older release or give a pinException"
            )
        elif now - published >= COOLDOWN and pin.exception:
            report.review.append(
                f"{label}@{pin.version} is past its cooldown; its pinException can go"
            )
        newer = {v: when for v, when in releases.items() if _key(v) > _key(pin.version)}
        ripe = [v for v, when in newer.items() if now - when >= COOLDOWN]
        best = max(ripe, key=_key) if ripe else pin.version
        if ripe:
            report.changed.append(
                f"{label} {best} ({_day(newer[best])}) is newer than the pinned {pin.version}; "
                f"re-pin it in {MCP_SERVERS_NAME} with its publishedAt"
            )
        else:
            report.pins.append(f"{name}: {pin.package}@{pin.version}")
        waiting = [v for v in newer if _key(v) > _key(best)]  # newer than any ripe one: young
        if waiting:
            soon = max(waiting, key=_key)
            report.notes.append(
                f"{label} {soon} is in its cooldown until {_day(newer[soon] + COOLDOWN)}"
            )
