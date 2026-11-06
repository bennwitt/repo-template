import json
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from repo_template.maintenance import CheckCache, automatic_reason, freshness_warning, read_json
from repo_template.release_policy import COOLDOWN

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


def test_freshness_boundary_force_and_configuration_changes(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    calls = []

    def inspect():
        calls.append(1)
        return {"available_ref": "abc"}

    def run(at=NOW, **kwargs):
        return CheckCache(tmp_path, path=path, now=at, **kwargs).inspect(
            "source", {"ref": "main"}, inspect
        )

    run()
    original = path.read_bytes()
    run(NOW + timedelta(hours=23, minutes=59))
    assert len(calls) == 1 and path.read_bytes() == original
    run(NOW + timedelta(hours=24))
    assert len(calls) == 2
    run(NOW + timedelta(hours=24), force=True)
    assert len(calls) == 3
    CheckCache(tmp_path, path=path, now=NOW).inspect("source", {"ref": "other"}, inspect)
    assert len(calls) == 4


def test_failed_checks_keep_last_success_and_retry(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    CheckCache(tmp_path, path=path, now=NOW).inspect("source", {}, lambda: {"version": "1"})
    previous = read_json(path)["sources"]["source"]["last_successful_check_at"]

    def failed():
        raise OSError("offline")

    cache = CheckCache(tmp_path, path=path, now=NOW + timedelta(days=1))
    with pytest.raises(OSError):
        cache.inspect("source", {}, failed)
    record = read_json(path)["sources"]["source"]
    assert record["last_successful_check_at"] == previous
    assert record["failure_reason"] == "offline"
    assert record["last_checked_at"] != previous
    assert cache.inspect("source", {}, lambda: {"version": "2"}) == {"version": "2"}


def test_dry_run_and_corrupt_cache(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("invalid")
    cache = CheckCache(tmp_path, path=path, now=NOW, dry_run=True)
    assert cache.inspect("source", {}, lambda: {"ok": True}) == {"ok": True}
    assert path.read_text() == "invalid"


@pytest.mark.parametrize("age", [0, -1, float("inf"), float("nan")])
def test_invalid_freshness_threshold(tmp_path: Path, age: float) -> None:
    with pytest.raises(ValueError, match="finite positive"):
        CheckCache(tmp_path, max_age_hours=age)


def test_release_cooldown_is_one_day_everywhere() -> None:
    from repo_template import mcp, pins

    assert mcp.COOLDOWN == pins.COOLDOWN == COOLDOWN == timedelta(days=1)


def test_automatic_policy_is_not_just_a_publisher_allowlist() -> None:
    sources = {"sources": {"official/source": {}}}
    assert (
        automatic_reason("official/source", sources, adding=False, changed=["SKILL.md"], notes=[])
        is None
    )
    for source, adding, changed, notes in (
        ("new/source", False, ["SKILL.md"], []),
        ("official/source", True, ["SKILL.md"], []),
        ("official/source", False, ["scripts/setup.sh"], []),
        ("official/source", False, ["SKILL.md"], ["permissions changed"]),
    ):
        assert automatic_reason(source, sources, adding=adding, changed=changed, notes=notes)


def test_partial_inspection_never_claims_catalog_freshness(tmp_path, monkeypatch):
    monkeypatch.setenv("REPO_TEMPLATE_CACHE", str(tmp_path / "cache"))
    cache = CheckCache(tmp_path, now=NOW)
    cache.inspect("one", {}, lambda: {"ok": True})
    assert freshness_warning(tmp_path, now=NOW)
    cache.inspect("two", {}, lambda: {"ok": True})
    cache.complete()
    assert freshness_warning(tmp_path, now=NOW) is None
    assert freshness_warning(tmp_path, now=NOW + timedelta(hours=24))
    CheckCache(tmp_path, now=NOW + timedelta(hours=24)).inspect("one", {}, lambda: {})
    assert freshness_warning(tmp_path, now=NOW + timedelta(hours=24))
    agents = tmp_path / ".agents"
    agents.mkdir()
    (agents / "skill-packs.json").write_text('{"new":{"skills":[]}}')
    assert freshness_warning(tmp_path, now=NOW)


def test_reference_source_alias_and_unknown_source(tmp_path, monkeypatch, capsys):
    from repo_template import cli

    agents = tmp_path / ".agents"
    agents.mkdir()
    (agents / ".skill-lock.json").write_text('{"skills":{}}')
    (agents / "skill-sources.json").write_text(
        json.dumps(
            {"sources": {}, "references": {"docs": {"kind": "github", "source": "owner/docs"}}}
        )
    )

    class GitHub:
        def commit(self, source, ref):
            assert source == "owner/docs"
            return "a" * 40, "b" * 40

    monkeypatch.setattr(cli, "GhApi", GitHub)
    args = Namespace(
        force=True, max_age_hours=24, dry_run=True, source=["github:owner/docs"], json=True
    )
    assert cli._upstream(tmp_path, args) == 0
    assert json.loads(capsys.readouterr().out)["available"]["docs"] == "a" * 40
    with pytest.raises(ValueError, match="unknown --source"):
        cli._validate_sources(tmp_path, ["typo"])


def test_immutable_blob_cache_checks_integrity_and_avoids_redownload(tmp_path):
    from repo_template.catalog import blob_sha
    from repo_template.maintenance import CachedGitHub

    data = b"reviewed immutable content"
    sha = blob_sha(data)
    calls = []

    class GitHub:
        def blob(self, source, revision):
            calls.append(revision)
            return data

    cache = CheckCache(tmp_path, path=tmp_path / "cache.json", force=True)
    github = CachedGitHub(GitHub(), cache, {})
    assert github.blob("owner/repo", sha) == github.blob("owner/repo", sha) == data
    assert calls == [sha]
    (tmp_path / "objects" / sha).write_bytes(b"corrupt")
    assert github.blob("owner/repo", sha) == data and calls == [sha, sha]
