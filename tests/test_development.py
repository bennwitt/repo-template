from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from repo_template.development import check_development, load_development
from repo_template.upstream import NetworkError, NotFound, Report

NOW = datetime(2026, 11, 2, 22, tzinfo=UTC)


def baseline(path: Path, **changes: object) -> None:
    data = {
        "schema": 1,
        "protocol": "2026-07-28",
        "packages": {
            "sdk": {
                "registry": "pypi",
                "package": "mcp",
                "version": "2.3.0",
                "publishedAt": "2026-10-02T22:00:00Z",
            }
        },
        **changes,
    }
    (path / "mcp-development.json").write_text(json.dumps(data))


class Registry:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def releases(self, registry: str, package: str) -> dict[str, datetime]:
        if self.error:
            raise self.error
        assert (registry, package) == ("pypi", "mcp")
        return {
            "2.3.0": datetime(2026, 10, 2, 22, tzinfo=UTC),
            "2.4.0": NOW - timedelta(days=8),
            "2.5.0": NOW - timedelta(days=1),
        }


def test_development_drift_is_read_only_and_respects_cooldown(tmp_path: Path) -> None:
    baseline(tmp_path)
    before = (tmp_path / "mcp-development.json").read_bytes()
    report = Report()
    check_development(tmp_path, Registry(), NOW, report)
    assert report.exit_code == 1
    assert "2.4.0" in report.changed[0] and "compatibility tests" in report.changed[0]
    assert "--upgrade" not in report.changed[0]
    assert "2.5.0" in report.notes[0]
    assert report.pin_changes == 1
    assert (tmp_path / "mcp-development.json").read_bytes() == before


def test_missing_catalog_is_backwards_compatible(tmp_path: Path) -> None:
    assert load_development(tmp_path) == {}


@pytest.mark.parametrize(
    "changes",
    [{"schema": 2}, {"protocol": "latest"}, {"packages": {}}, {"packages": {"sdk": None}}],
)
def test_invalid_development_catalog_fails(tmp_path: Path, changes: dict[str, object]) -> None:
    baseline(tmp_path, **changes)
    with pytest.raises(ValueError):
        load_development(tmp_path)


def test_missing_package_needs_review_and_network_failure_propagates(tmp_path: Path) -> None:
    baseline(tmp_path)
    report = Report()
    check_development(tmp_path, Registry(NotFound("gone")), NOW, report)
    assert report.exit_code == 2
    with pytest.raises(NetworkError):
        check_development(tmp_path, Registry(NetworkError("offline")), NOW, Report())
