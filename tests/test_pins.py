"""MCP pins against their registries: only a release past its cooldown is offered."""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from repo_template import cli
from repo_template.mcp import load_mcp_servers
from repo_template.pins import check_pins, npm_releases, pypi_releases
from repo_template.upstream import NetworkError, NotFound, Report

NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)
PUBLISHED = "2026-09-01T10:00:00Z"


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


class FakeRegistry:
    def __init__(self, releases: dict[str, datetime] | Exception) -> None:
        self.data, self.asked = releases, []

    def releases(self, registry: str, package: str) -> dict[str, datetime]:
        self.asked.append((registry, package))
        if isinstance(self.data, Exception):
            raise self.data
        return dict(self.data)


def _servers(tmp_path: Path, **pin: Any) -> Any:
    raw = {
        "registry": "npm",
        "package": "@x/mcp",
        "version": "1.0.0",
        "publishedAt": PUBLISHED,
        **pin,
    }
    server = {
        "scope": "global",
        "command": "npx",
        "args": ["-y", f"@x/mcp@{raw['version']}"],
        "pin": raw,
        "source": "s",
        "why": "w",
    }
    agents = tmp_path / ".agents"
    agents.mkdir(parents=True, exist_ok=True)
    (agents / "mcp-servers.json").write_text(json.dumps({"schema": 1, "servers": {"x": server}}))
    return load_mcp_servers(agents)


def _report(tmp_path: Path, releases: dict[str, datetime] | Exception, **pin: Any) -> Report:
    report = Report()
    check_pins(_servers(tmp_path, **pin), FakeRegistry(releases), NOW, report)
    return report


def test_a_pin_with_nothing_newer_is_current(tmp_path: Path) -> None:
    report = _report(tmp_path, {"1.0.0": _at(PUBLISHED), "0.9.0": _at("2026-08-01T00:00:00Z")})

    assert report.pins == ["x: @x/mcp@1.0.0"]
    assert report.changed == report.review == report.notes == []


def test_the_newest_release_past_its_cooldown_is_offered(tmp_path: Path) -> None:
    releases = {
        "1.0.0": _at(PUBLISHED),
        "1.0.2": NOW - timedelta(days=8),
        "1.0.10": NOW - timedelta(days=7),  # numeric order, not text order
        "1.1.0": NOW - timedelta(days=2),
    }

    report = _report(tmp_path, releases)

    assert report.changed == [
        "x: npm @x/mcp 1.0.10 is newer than the pinned 1.0.0; re-pin it in mcp-servers.json "
        "(args and pin) with publishedAt 2026-10-07T12:00:00Z"
    ]
    assert report.notes == ["x: npm @x/mcp 1.1.0 is in its cooldown until 2026-10-19T12:00:00Z"]
    assert report.pins == [] and report.exit_code == 1


def test_a_release_still_in_its_cooldown_is_only_noted(tmp_path: Path) -> None:
    report = _report(tmp_path, {"1.0.0": _at(PUBLISHED), "1.0.1": NOW - timedelta(days=6)})

    assert report.changed == [] and report.exit_code == 0
    assert report.notes == ["x: npm @x/mcp 1.0.1 is in its cooldown until 2026-10-15T12:00:00Z"]


@pytest.mark.parametrize(
    ("releases", "pin", "expected"),
    [
        (
            {"0.9.0": _at("2026-08-01T00:00:00Z")},
            {},
            "x: npm @x/mcp@1.0.0 was yanked or deprecated, or never published; pin another release",
        ),
        (
            {"1.0.0": _at("2026-09-02T10:00:00Z")},
            {},
            "x: npm @x/mcp@1.0.0 was published 2026-09-02T10:00:00Z, not 2026-09-01T10:00:00Z "
            "as mcp-servers.json records",
        ),
        (
            {"1.0.0": _at("2026-10-12T22:33:00Z")},
            {"publishedAt": "2026-10-12T22:33:00Z"},
            "x: npm @x/mcp@1.0.0 is inside its cooldown until 2026-10-19T22:33:00Z; pin an older "
            "release "
            "or give a pinException",
        ),
        (
            {"1.0.0": _at(PUBLISHED)},
            {"pinException": "fixes the Node 20 crash"},
            "x: npm @x/mcp@1.0.0 is past its cooldown; its pinException can go",
        ),
        (NotFound("404"), {}, "x: npm @x/mcp isn't on npm any more"),
    ],
)
def test_a_pin_that_needs_a_decision_is_for_review(
    tmp_path: Path, releases: Any, pin: dict[str, str], expected: str
) -> None:
    report = _report(tmp_path, releases, **pin)

    assert report.review == [expected] and report.exit_code == 2


def test_a_young_pin_with_a_reason_is_accepted(tmp_path: Path) -> None:
    young = "2026-10-12T22:33:00Z"

    report = _report(tmp_path, {"1.0.0": _at(young)}, publishedAt=young, pinException="why")

    assert report.review == [] and report.pins == ["x: @x/mcp@1.0.0"]


def test_registry_documents_give_only_final_live_releases() -> None:
    npm = {
        "time": {"1.0.0": PUBLISHED, "1.1.0-beta.1": PUBLISHED, "1.0.1": PUBLISHED, "2.0.0": 5},
        "versions": {
            "1.0.0": {},
            "1.1.0-beta.1": {},
            "1.0.1": {"deprecated": "broken"},
            "2.0.0": {},
            "3.0.0": {},  # no time recorded
        },
    }
    pypi = {
        "releases": {
            "3.0.0": [
                {"upload_time_iso_8601": "2026-10-12T22:40:00.1Z", "yanked": False},
                {"upload_time_iso_8601": "2026-10-12T22:33:00.5Z", "yanked": False},
            ],
            "2.0.5": [{"upload_time_iso_8601": PUBLISHED, "yanked": True}],
            "3.0.1rc1": [{"upload_time_iso_8601": PUBLISHED}],
            "2.0.0": [],
        }
    }

    assert npm_releases(npm) == {"1.0.0": _at(PUBLISHED)}
    assert pypi_releases(pypi) == {"3.0.0": _at("2026-10-12T22:33:00.5Z")}


def test_upstream_checks_the_pins_and_a_registry_failure_exits_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "standards"
    _servers(root)
    registry = FakeRegistry({"1.0.0": _at(PUBLISHED), "1.0.1": NOW - timedelta(days=30)})
    monkeypatch.setattr(cli, "upstream_report", lambda root, github: Report())
    monkeypatch.setattr(cli, "GhApi", lambda: None)
    monkeypatch.setattr(cli, "HttpRegistry", lambda: registry)

    assert cli._upstream(root) == 1
    assert "@x/mcp 1.0.1" in capsys.readouterr().out
    assert registry.asked == [("npm", "@x/mcp")]

    registry.data = NetworkError("GET https://registry.npmjs.org/@x%2Fmcp: timed out")
    assert cli._upstream(root) == 3
    assert "timed out" in capsys.readouterr().err


def test_two_young_releases_note_the_newest_and_a_boundary_pin_is_ripe(tmp_path: Path) -> None:
    releases = {
        "1.0.0": _at(PUBLISHED),
        "1.0.9": NOW - timedelta(days=7),  # exactly 7 days: ripe
        "1.0.10": NOW - timedelta(days=3),
        "1.0.11": NOW - timedelta(days=1),
    }

    report = _report(tmp_path, releases)

    assert report.changed[0].startswith("x: npm @x/mcp 1.0.9 is newer")
    assert report.notes == ["x: npm @x/mcp 1.0.11 is in its cooldown until 2026-10-20T12:00:00Z"]


def test_a_pin_spelled_with_trailing_zeros_matches_its_release(tmp_path: Path) -> None:
    report = _report(tmp_path, {"1.0": _at(PUBLISHED)})

    assert report.review == [] and report.pins == ["x: @x/mcp@1.0.0"]


def test_a_recorded_time_on_the_day_before_is_for_review(tmp_path: Path) -> None:
    """Its cutoff would be the release's own day, so npm would refuse the pinned version."""
    report = _report(
        tmp_path, {"1.0.0": _at("2026-09-02T00:00:20Z")}, publishedAt="2026-09-01T23:59:50Z"
    )

    assert report.review and "was published 2026-09-02T00:00:20Z" in report.review[0]


def test_a_review_and_a_change_together_exit_2(tmp_path: Path) -> None:
    releases = {"1.0.0": _at("2026-09-02T10:00:00Z"), "1.1.0": NOW - timedelta(days=9)}

    report = _report(tmp_path, releases)

    assert report.review and report.changed and report.exit_code == 2


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


@pytest.mark.parametrize(
    ("outcome", "error"),
    [
        (urllib.error.HTTPError("u", 404, "nf", {}, None), NotFound),  # type: ignore[arg-type]
        (urllib.error.HTTPError("u", 500, "e", {}, None), NetworkError),  # type: ignore[arg-type]
        (ConnectionResetError("reset"), NetworkError),
        (http.client.IncompleteRead(b"x"), NetworkError),
        (b"not json", NetworkError),
        (b"[1, 2]", NetworkError),
        (b'{"releases": null}', NetworkError),
        (b'{"releases": {"1.0": [{"upload_time_iso_8601": "2026-09-01T10:00:00"}]}}', NetworkError),
    ],
)
def test_every_registry_failure_is_a_network_error_or_not_found(
    monkeypatch: pytest.MonkeyPatch, outcome: object, error: type[Exception]
) -> None:
    from repo_template import pins

    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        if isinstance(outcome, BaseException):
            raise outcome
        return _Response(outcome)  # type: ignore[arg-type]

    monkeypatch.setattr(pins.urllib.request, "urlopen", urlopen)

    with pytest.raises(error):
        pins.HttpRegistry().releases("pypi", "msmcp-azure")


def test_extras_are_dropped_and_scopes_quoted_in_the_registry_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from repo_template import pins

    asked: list[str] = []

    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        asked.append(request.full_url)
        return _Response(b'{"releases": {}, "time": {}, "versions": {}}')

    monkeypatch.setattr(pins.urllib.request, "urlopen", urlopen)

    pins.HttpRegistry().releases("pypi", "msmcp-azure[extra]")
    pins.HttpRegistry().releases("npm", "@playwright/mcp")

    assert asked == [
        "https://pypi.org/pypi/msmcp-azure/json",
        "https://registry.npmjs.org/@playwright%2Fmcp",
    ]


def test_upgrade_is_suggested_only_for_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "standards"
    _servers(root)
    registry = FakeRegistry({"1.0.0": _at(PUBLISHED), "1.0.1": NOW - timedelta(days=30)})
    monkeypatch.setattr(cli, "upstream_report", lambda root, github: Report())
    monkeypatch.setattr(cli, "GhApi", lambda: None)
    monkeypatch.setattr(cli, "HttpRegistry", lambda: registry)

    assert cli._upstream(root) == 1
    assert "--upgrade" not in capsys.readouterr().out
