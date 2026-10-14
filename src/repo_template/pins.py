"""Newer releases of the packages MCP servers pin, for `globals --upstream`.

A release is offered once it is a week old (COOLDOWN), so a bad release has time to be caught
and pulled first; pre-releases, and releases yanked or deprecated, never are. A pin younger than
that needs a `pinException` saying why, and is reported once the exception is no longer needed.
Versions are plain final releases (1.2.3; 1.2 and 1.2.0 are the same one); a post-release or
local version isn't offered or pinned.
"""

from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from repo_template.mcp import MCP_SERVERS_NAME, Server
from repo_template.upstream import NetworkError, NotFound, Report, clean

COOLDOWN = timedelta(days=7)
FINAL = re.compile(r"\d+(?:\.\d+)*")  # 1.2.3: a final release, the only kind offered
EXTRAS = re.compile(r"\[[^\]]*\]$")
URLS = {"npm": "https://registry.npmjs.org/{}", "pypi": "https://pypi.org/pypi/{}/json"}


class Registry(Protocol):
    def releases(self, registry: str, package: str) -> dict[str, datetime]:
        """Each final release of `package` that wasn't yanked or deprecated, and when it was
        published. Raises NotFound for an unknown package, NetworkError otherwise."""
        ...


def _time(value: str) -> datetime:
    when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise ValueError(f"{value!r} has no time zone")
    return when


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
    releases = document.get("releases")
    if not isinstance(releases, dict):  # deprecated in the JSON API: say so, don't report "yanked"
        raise ValueError("no 'releases' in PyPI's response")
    found = {}
    for version, files in releases.items():
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
        name = EXTRAS.sub("", package)  # msmcp-azure[x] is the msmcp-azure project
        url = URLS[registry].format(urllib.parse.quote(name, safe="@"))
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                document = json.loads(response.read())
            if not isinstance(document, dict):
                raise ValueError("not a JSON object")
            return (npm_releases if registry == "npm" else pypi_releases)(document)
        except urllib.error.HTTPError as exc:
            error = NotFound if exc.code == 404 else NetworkError
            raise error(f"GET {url}: HTTP {exc.code}") from None
        except (OSError, http.client.HTTPException) as exc:  # URLError, timeouts, resets
            raise NetworkError(f"GET {url}: {clean(str(exc))}") from None
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise NetworkError(f"GET {url}: unexpected response ({clean(str(exc))})") from None


def _key(version: str) -> tuple[int, ...]:
    """1.2 and 1.2.0 are the same release."""
    parts = [int(part) for part in version.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _stamp(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        check_pin(
            name,
            label,
            pin.version,
            pin.published_at,
            releases,
            now,
            report,
            record=MCP_SERVERS_NAME,
            move=f"re-pin it with `repo-template globals --upgrade mcp:{name}`",
            exception=pin.exception,
        )


def check_pin(
    name: str,
    label: str,
    version: str,
    published_at: str,
    releases: Mapping[str, datetime],
    now: datetime,
    report: Report,
    *,
    record: str,
    move: str,
    exception: str | None = None,
    below: str | None = None,
) -> None:
    """One pin against its package's final releases (`releases`, version -> published): `record`
    is the file that holds it, `move` how to move it; `below` bounds the versions offered."""
    by_key = {_key(release): when for release, when in releases.items()}
    published = by_key.get(_key(version))
    recorded = _time(published_at)
    if published is None:
        report.review.append(
            f"{label}@{version} was yanked or deprecated, or never published; pin another release"
        )
    elif (
        abs(published - recorded) > timedelta(minutes=1)
        or recorded.astimezone(UTC).date() != published.astimezone(UTC).date()
    ):  # the cutoff a pin runs with is the UTC midnight after its recorded day
        report.review.append(
            f"{label}@{version} was published {_stamp(published)}, not {published_at} as "
            f"{record} records"
        )
    elif now - published < COOLDOWN and not exception:
        report.review.append(
            f"{label}@{version} is inside its cooldown until {_stamp(published + COOLDOWN)}; pin "
            f"an older release or give a pinException"
        )
    elif now - published >= COOLDOWN and exception:
        report.review.append(f"{label}@{version} is past its cooldown; its pinException can go")
    newer = {
        release: when
        for release, when in releases.items()
        if _key(release) > _key(version) and (below is None or _key(release) < _key(below))
    }
    ripe = [release for release, when in newer.items() if now - when >= COOLDOWN]
    best = max(ripe, key=_key) if ripe else version
    if ripe:
        report.changed.append(f"{label} {best} is newer than the pinned {version}; {move}")
        report.pin_changes += 1
    else:
        report.pins.append(f"{name}: {label.split(' ', 2)[-1]}@{version}")
    waiting = [release for release in newer if _key(release) > _key(best)]  # all still young
    if waiting:
        soon = max(waiting, key=_key)
        report.notes.append(
            f"{label} {soon} is in its cooldown until {_stamp(newer[soon] + COOLDOWN)}"
        )
