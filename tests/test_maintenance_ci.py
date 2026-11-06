import json

import pytest

from repo_template import maintenance_ci as ci
from repo_template.maintenance_ci import BRANCH, allowed_path, merge_ready


def ready():
    return {
        "headRefOid": "a" * 40,
        "headRefName": BRANCH,
        "baseRefName": "main",
        "isDraft": False,
        "mergeStateStatus": "CLEAN",
        "reviewDecision": "APPROVED",
        "statusCheckRollup": [
            {"name": name, "conclusion": "SUCCESS"}
            for name in [
                "quality",
                "python-mcp",
                "typescript-mcp",
                "langchain-mcp",
                "legacy-langchain",
            ]
        ],
    }


def test_merge_requires_the_validated_head_and_all_expected_checks():
    pr = ready()
    assert merge_ready(pr, "a" * 40)
    assert not merge_ready(pr, "b" * 40)
    pr["statusCheckRollup"].pop()
    assert not merge_ready(pr, "a" * 40)


@pytest.mark.parametrize("conclusion", ["FAILURE", "SKIPPED", "CANCELLED", None])
def test_unsuccessful_checks_never_allow_merge(conclusion):
    pr = ready()
    pr["statusCheckRollup"][0]["conclusion"] = conclusion
    assert not merge_ready(pr, "a" * 40)


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        "src/run.py",
        ".git/config",
        ".agents/skills/skill-scanner/SKILL.md",
        ".agents/packs/x/script.py",
        ".agents/packs/x/../../config",
    ],
)
def test_publication_rejects_executable_or_privilege_changes(path):
    assert not allowed_path(path)


def test_catalog_documentation_is_publishable():
    assert allowed_path(".agents/packs/langchain-fundamentals/SKILL.md")
    assert allowed_path(".agents/skill-sources.json")


def test_activation_requires_credentials_settings_and_required_checks(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(ValueError, match="scoped"):
        ci.activation("owner/repo")
    monkeypatch.setenv("GH_TOKEN", "fixture-only")
    monkeypatch.setenv("MAINTENANCE_BOT_LOGIN", "maintenance[bot]")
    repo = {"allow_auto_merge": True, "allow_squash_merge": True}
    protection = {"required_status_checks": {"contexts": sorted(ci.CHECKS)}}
    monkeypatch.setattr(
        ci,
        "run",
        lambda *args, **kw: json.dumps(
            protection if args[-1].endswith("protection") else repo
        ).encode(),
    )
    ci.activation("owner/repo")
    protection["required_status_checks"]["contexts"].pop()
    with pytest.raises(ValueError, match="require quality"):
        ci.activation("owner/repo")


@pytest.mark.parametrize(
    "changed", ["none", "head", "marker", "checks", "attestation", "app", "behind"]
)
def test_merge_stand_in_requires_app_admission_for_tested_head(monkeypatch, changed):
    monkeypatch.setenv("MAINTENANCE_BOT_LOGIN", "maintenance[bot]")
    pr = ready()
    pr.update(body=f"<!-- repo-template-head:{'a' * 40} -->", author={"login": "maintenance[bot]"})
    attestation = {
        "name": "maintenance-admission",
        "head_sha": "a" * 40,
        "external_id": "a" * 40,
        "conclusion": "success",
        "app": {"slug": "maintenance"},
    }
    if changed in {"head", "marker"}:
        pr["headRefOid"] = "b" * 40
    if changed == "marker":
        pr["body"] = f"<!-- repo-template-head:{'b' * 40} -->"
    if changed == "checks":
        pr["statusCheckRollup"].pop()
    if changed == "app":
        attestation["app"] = {"slug": "another-app"}
    if changed == "behind":
        pr["mergeStateStatus"] = "BEHIND"
    if changed == "none":
        pr["author"] = {"login": "app/maintenance", "is_bot": True}
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        if args[1:3] == ("pr", "list"):
            return b'[{"number":1}]'
        if args[1:3] == ("pr", "view"):
            return json.dumps(pr).encode()
        if args[1] == "api":
            return json.dumps(
                {"check_runs": [] if changed == "attestation" else [attestation]}
            ).encode()
        return b""

    monkeypatch.setattr(ci, "run", run)
    if changed == "behind":
        assert ci.merge_existing("owner/repo")["headRefOid"] == "a" * 40
        assert not any(c[1:3] == ("pr", "merge") for c in calls)
    elif changed == "none":
        assert ci.merge_existing("owner/repo")
        assert "--match-head-commit" in calls[-1] and "a" * 40 in calls[-1]
    else:
        with pytest.raises(ValueError):
            ci.merge_existing("owner/repo")
        assert not any(c[1:3] == ("pr", "merge") for c in calls)
    assert not any("--admin" in c or "--force" in c for c in calls)


def test_prepare_rejects_ineligible_files_and_publication_checks_artifact(tmp_path, monkeypatch):
    report = tmp_path / "upgrade.json"
    report.write_text(json.dumps({"applied": ["skill"], "result": {"errors": []}}))
    monkeypatch.setattr(ci, "run", lambda *a, **kw: b"src/unsafe.py\0")
    with pytest.raises(ValueError, match="boundary"):
        ci.prepare(tmp_path, report)
    evidence = {"paths": [".agents/skills/s/SKILL.md"], "patch_sha256": "wrong"}
    (tmp_path / "evidence.json").write_text(json.dumps(evidence))
    (tmp_path / "catalog.patch").write_text("changed")
    with pytest.raises(ValueError, match="integrity"):
        ci.publish(tmp_path, "owner/repo")


def test_behind_pr_refresh_publishes_exact_tested_tree_without_force(tmp_path, monkeypatch):
    import hashlib

    patch = b"synthetic patch"
    path = ".agents/skills/s/SKILL.md"
    (tmp_path / "catalog.patch").write_bytes(patch)
    (tmp_path / "evidence.json").write_text(
        json.dumps(
            {"paths": [path], "patch_sha256": hashlib.sha256(patch).hexdigest(), "base": "a" * 40}
        )
    )
    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        if args[1:3] == ("rev-parse", "HEAD"):
            return ("a" * 40).encode()
        if args[1:3] == ("rev-parse", "FETCH_HEAD"):
            return ("b" * 40).encode()
        if "ls-remote" in args:
            return ("a" * 40 + "\trefs/heads/main\n").encode()
        if args[1:3] == ("diff", "--cached"):
            return (path + "\0").encode()
        if "write-tree" in args:
            return ("c" * 40).encode()
        if "commit-tree" in args:
            assert "b" * 40 in args and "a" * 40 in args and "c" * 40 in args
            return ("d" * 40).encode()
        return b"{}"

    monkeypatch.setattr(ci, "run", run)
    ci.publish(tmp_path, "owner/repo", refresh={"number": 1, "headRefOid": "b" * 40})
    assert any(c[0][1:3] == ("pr", "edit") for c in calls)
    assert not any("--force" in c[0] or "--admin" in c[0] for c in calls)
    check = next(c[1]["input"] for c in calls if c[0][1:3] == ("api", "--method"))
    assert json.loads(check)["head_sha"] == "d" * 40
    assert "d" * 40 in (tmp_path / "pr-body.md").read_text()
