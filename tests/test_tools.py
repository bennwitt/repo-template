"""Per-machine tools: one pin file, validated, and checked against npm and GitHub releases."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from repo_template.tools import (
    TOOLS_NAME,
    check_machine_tools,
    github_releases,
    load_machine_tools,
)
from repo_template.upstream import Report

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)
DIGEST = "a" * 64


def _stamp(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(tmp_path: Path, tools: dict[str, Any]) -> Path:
    agents = tmp_path / ".agents"
    agents.mkdir(exist_ok=True)
    (agents / TOOLS_NAME).write_text(json.dumps({"schema": 1, "tools": tools}))
    return agents


def _npm(version: str = "1.0.0", **extra: object) -> dict[str, object]:
    return {
        "registry": "npm",
        "package": "lsp",
        "version": version,
        "publishedAt": _stamp(NOW - 60 * DAY),
        "why": "w",
        **extra,
    }


def _github(digest: str = DIGEST) -> dict[str, object]:
    return {
        "registry": "github",
        "package": "o/tool",
        "tag": "tool_{version}",
        "version": "1.0.0",
        "publishedAt": _stamp(NOW - 60 * DAY),
        "assets": {"linux-amd64": {"file": "tool-linux-amd64.tar.gz", "sha256": digest}},
        "why": "w",
    }


class FakeRegistry:
    def __init__(self, releases: dict[str, datetime]) -> None:
        self.by_version = releases

    def releases(self, registry: str, package: str) -> dict[str, datetime]:
        return self.by_version


class FakeReleases:
    def __init__(self, releases: list[dict[str, Any]]) -> None:
        self.listed = releases

    def releases(self, source: str) -> list[dict[str, Any]]:
        return self.listed


def _release(version: str, when: datetime, digest: str = DIGEST, **extra: object) -> dict[str, Any]:
    return {
        "tag_name": f"tool_{version}",
        "published_at": _stamp(when),
        "assets": [{"name": "tool-linux-amd64.tar.gz", "digest": f"sha256:{digest}"}],
        **extra,
    }


def test_the_shipped_pin_file_is_valid() -> None:
    tools = load_machine_tools(ROOT / ".agents")

    assert {"azd", "codex", "playwright-cli", "pyright", "typescript"} <= set(tools)
    assert set(tools["azd"].assets) == {
        "darwin-amd64",
        "darwin-arm64",
        "linux-amd64",
        "linux-arm64",
    }


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({**_npm(), "registry": "pip"}, "needs 'registry'"),
        (_npm("1.0.0-beta"), "final release"),
        ({**_npm(), "why": ""}, "needs a 'why'"),
        ({**_npm(), "publishedAt": "2026-10-01"}, "time with its zone"),
        ({**_npm(), "below": "next"}, "'below' must be a version"),
        ({**_npm(), "tag": "v{version}"}, "only a github tool"),
        ({**_github(), "tag": "v1"}, "holding {version}"),
        (
            {**_github(), "assets": {"windows-amd64": {"file": "t.zip", "sha256": DIGEST}}},
            "platforms",
        ),
        (_github(digest="nothex"), "64 hex digits"),
        ({**_github(), "package": "not a repo"}, "owner/repo"),
    ],
)
def test_a_pin_file_that_cant_be_trusted_is_refused(
    tmp_path: Path, entry: dict[str, object], message: str
) -> None:
    agents = _write(tmp_path, {"tool": entry})

    with pytest.raises(ValueError, match=message):
        load_machine_tools(agents)


def test_github_releases_keeps_final_releases_and_their_digests() -> None:
    found = github_releases(
        [
            _release("1.1.0", NOW - 9 * DAY),
            _release("1.2.0", NOW - DAY, prerelease=True),
            _release("1.3.0", NOW, draft=True),
            {"tag_name": "other_9.9.9", "published_at": _stamp(NOW), "assets": []},
        ],
        "tool_{version}",
    )

    assert found == {"1.1.0": (NOW - 9 * DAY, {"tool-linux-amd64.tar.gz": DIGEST})}


def test_a_newer_npm_release_is_a_change_below_its_bound(tmp_path: Path) -> None:
    tools = load_machine_tools(_write(tmp_path, {"lsp": _npm(below="2")}))
    registry = FakeRegistry(
        {"1.0.0": NOW - 60 * DAY, "1.4.0": NOW - 10 * DAY, "2.0.0": NOW - 30 * DAY}
    )
    report = Report()

    check_machine_tools(tools, registry, FakeReleases([]), NOW, report)

    assert report.changed == [
        "lsp: npm lsp 1.4.0 is newer than the pinned 1.0.0; update its version and publishedAt "
        "in machine-tools.json"
    ]
    assert report.pin_changes == 1 and report.exit_code == 1


def test_a_github_tool_is_checked_and_its_digests_compared(tmp_path: Path) -> None:
    tools = load_machine_tools(_write(tmp_path, {"tool": _github()}))
    releases = FakeReleases(
        [_release("1.1.0", NOW - 2 * DAY), _release("1.0.0", NOW - 60 * DAY, digest="b" * 64)]
    )
    report = Report()

    check_machine_tools(tools, FakeRegistry({}), releases, NOW, report)

    assert report.changed == []  # 1.1.0 is still in its cooldown
    assert report.notes == [
        "tool: github o/tool 1.1.0 is in its cooldown until 2026-10-19T12:00:00Z"
    ]
    assert len(report.review) == 1 and "has sha256 " + "b" * 64 in report.review[0]
