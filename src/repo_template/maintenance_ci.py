"""Publication guardrails for the existing catalog maintenance workflow.

The updater still owns discovery, admission and application. This module only packages
validated changes and publishes their PR; it never executes candidate-provided code.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

BRANCH = "automation/catalog-maintenance"
CHECKS = {"quality", "python-mcp", "typescript-mcp", "langchain-mcp", "legacy-langchain"}
GENERATED = {
    "README.md",
    "CHANGELOG.md",
    "THIRD_PARTY_NOTICES.md",
    ".agents/.skill-lock.json",
    ".agents/skill-sources.json",
    ".agents/skill-overrides.json",
    ".agents/skill-packs.json",
}


def allowed_path(path: str) -> bool:
    parts = Path(path).parts
    if path in GENERATED:
        return True
    if ".." in parts or path.startswith("/") or "\\" in path:
        return False
    return (
        len(parts) >= 4
        and parts[:2] in {(".agents", "skills"), (".agents", "packs")}
        and parts[2] != "skill-scanner"
        and Path(path).suffix in {".md", ".txt", ".rst"}
    )


def merge_ready(pr: dict[str, Any], expected: str) -> bool:
    checks = pr.get("statusCheckRollup", [])
    return bool(
        pr.get("headRefOid") == expected
        and pr.get("headRefName") == BRANCH
        and pr.get("baseRefName") == "main"
        and not pr.get("isDraft")
        and pr.get("mergeStateStatus") == "CLEAN"
        and pr.get("reviewDecision") not in {"CHANGES_REQUESTED", "REVIEW_REQUIRED"}
        and checks
        and all(c.get("conclusion") == "SUCCESS" or c.get("state") == "SUCCESS" for c in checks)
        and {c.get("name", c.get("context")) for c in checks} >= CHECKS
    )


def run(*argv: str, input: bytes | None = None) -> bytes:
    done = subprocess.run(argv, input=input, capture_output=True, check=False)
    if done.returncode:
        raise ValueError(f"{argv[0]} {argv[1]} failed (exit {done.returncode})")
    return done.stdout


def activation(repository: str) -> None:
    """Fail closed when automation cannot verify the repository's required settings."""
    if not os.environ.get("GH_TOKEN") or not os.environ.get("MAINTENANCE_BOT_LOGIN"):
        raise ValueError("configure the scoped maintenance App token and bot identity")
    try:
        repo = json.loads(run("gh", "api", f"repos/{repository}"))
        protection = json.loads(run("gh", "api", f"repos/{repository}/branches/main/protection"))
    except ValueError as exc:
        raise ValueError(
            "cannot verify main protection; configure required checks and grant the App "
            "Administration read access"
        ) from exc
    required = protection.get("required_status_checks") or {}
    contexts = set(required.get("contexts", [])) | {
        c["context"] for c in required.get("checks", [])
    }
    if (
        not repo.get("allow_auto_merge")
        or not repo.get("allow_squash_merge")
        or not contexts >= CHECKS
    ):
        raise ValueError(
            "enable repository auto-merge and squash merge, and require quality plus all "
            "MCP fixture checks on main"
        )
    bypass = (protection.get("required_pull_request_reviews") or {}).get(
        "bypass_pull_request_allowances", {}
    )
    slug = os.environ["MAINTENANCE_BOT_LOGIN"].removesuffix("[bot]")
    if any(app.get("slug") == slug for app in bypass.get("apps", [])):
        raise ValueError("remove the maintenance App's branch-protection bypass")


def prepare(directory: Path, report_path: Path) -> None:
    report = json.loads(report_path.read_text())
    if report.get("result", {}).get("errors") or report.get("interrupted"):
        raise ValueError("updater reported local errors; publication refused")
    paths = run("git", "diff", "--name-only", "-z", "HEAD").decode().strip("\0").split("\0")
    paths = [p for p in paths if p]
    if any(not allowed_path(p) for p in paths):
        raise ValueError("candidate changes files outside the automatic catalog update boundary")
    if paths and not report.get("applied"):
        raise ValueError("candidate has changes without admitted skills")
    patch = run("git", "diff", "--binary", "HEAD")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "catalog.patch").write_bytes(patch)
    (directory / "evidence.json").write_text(
        json.dumps(
            {
                "base": run("git", "rev-parse", "HEAD").decode().strip(),
                "patch_sha256": hashlib.sha256(patch).hexdigest(),
                "paths": paths,
                "report": report,
            },
            indent=2,
        )
        + "\n"
    )


def publish(directory: Path, repository: str, *, refresh: dict[str, Any] | None = None) -> None:
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        raise ValueError("invalid repository identity")
    evidence = json.loads((directory / "evidence.json").read_text())
    patch = (directory / "catalog.patch").read_bytes()
    if hashlib.sha256(patch).hexdigest() != evidence["patch_sha256"] or any(
        not allowed_path(p) for p in evidence["paths"]
    ):
        raise ValueError("candidate artifact integrity or path validation failed")
    base = evidence["base"]
    if not re.fullmatch(r"[a-f0-9]{40}", base):
        raise ValueError("candidate base is not an immutable commit")
    current = run("git", "rev-parse", "HEAD").decode().strip()
    remote = run("git", "ls-remote", "origin", "refs/heads/main").decode().split()[0]
    if current != base or remote != base:
        raise ValueError("main changed after validation; rerun maintenance on the new base")
    if not evidence["paths"]:
        if refresh:
            run(
                "gh",
                "pr",
                "close",
                str(refresh["number"]),
                "--repo",
                repository,
                "--delete-branch",
                "--comment",
                "Re-evaluation on main found no eligible changes; closing the stale candidate.",
            )
        print("No automatically admitted changes to publish.")
        return
    # A credential-bearing job accepts data only; no candidate workflow, hook or code runs.
    run("git", "-c", "core.hooksPath=/dev/null", "apply", "--index", "-", input=patch)
    actual = run("git", "diff", "--cached", "--name-only", "-z").decode().strip("\0").split("\0")
    if sorted(actual) != sorted(evidence["paths"]):
        raise ValueError("patch contents do not match validated paths")
    identity = (
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "user.name=repo-template-maintenance[bot]",
        "-c",
        "user.email=repo-template-maintenance@users.noreply.github.com",
    )
    if refresh:
        # The new tree is exactly the tested base + patch. Preserve the old branch as a
        # parent, so publication is a fast-forward, with no force push or unchecked merge.
        run("git", "fetch", "--no-tags", "origin", f"refs/heads/{BRANCH}")
        old = run("git", "rev-parse", "FETCH_HEAD").decode().strip()
        if old != refresh["headRefOid"]:
            raise ValueError("maintenance branch changed during refresh; leaving it unchanged")
        tree = run("git", "write-tree").decode().strip()
        head = (
            run(
                *identity,
                "commit-tree",
                tree,
                "-p",
                old,
                "-p",
                base,
                "-m",
                "Re-evaluate catalog maintenance on current main",
            )
            .decode()
            .strip()
        )
    else:
        run("git", "-c", "core.hooksPath=/dev/null", "switch", "-c", BRANCH)
        run(*identity, "commit", "-m", "Refresh automatically admitted catalog skills")
        head = run("git", "rev-parse", "HEAD").decode().strip()
    # Never overwrite an existing branch: an open update is evaluated/merged before the next run.
    run("git", "-c", "core.hooksPath=/dev/null", "push", "origin", f"{head}:refs/heads/{BRANCH}")
    # This App-owned check binds admission to the actual published revision. An edited PR
    # body cannot re-authorize another head, and ordinary CI tokens cannot impersonate this App.
    run(
        "gh",
        "api",
        "--method",
        "POST",
        f"repos/{repository}/check-runs",
        "--input",
        "-",
        input=json.dumps(
            {
                "name": "maintenance-admission",
                "head_sha": head,
                "external_id": head,
                "status": "completed",
                "conclusion": "success",
            }
        ).encode(),
    )
    body = directory / "pr-body.md"
    body.write_text(
        "Refresh compatible catalog documentation after integrity and security "
        "evaluation. Repository quality gates and MCP fixtures passed before publication.\n\n"
        f"Validated base: `{base}`. Rollback: revert this PR.\n\n"
        "Candidates requiring review are retained in the maintenance run report.\n"
        f"\n<!-- repo-template-head:{head} -->\n"
    )
    if refresh:
        run(
            "gh",
            "pr",
            "edit",
            str(refresh["number"]),
            "--repo",
            repository,
            "--body-file",
            str(body),
        )
        return
    run(
        "gh",
        "pr",
        "create",
        "--repo",
        repository,
        "--head",
        BRANCH,
        "--base",
        "main",
        "--title",
        "Refresh agent capability catalog",
        "--body-file",
        str(body),
    )


def merge_existing(repository: str) -> bool | dict[str, Any]:
    rows = json.loads(
        run(
            "gh",
            "pr",
            "list",
            "--repo",
            repository,
            "--head",
            BRANCH,
            "--state",
            "open",
            "--json",
            "number",
        )
    )
    if not rows:
        return False
    number = str(rows[0]["number"])
    fields = (
        "headRefOid,headRefName,baseRefName,isDraft,mergeStateStatus,reviewDecision,"
        "statusCheckRollup,body,author"
    )
    pr = json.loads(run("gh", "pr", "view", number, "--repo", repository, "--json", fields))
    expected = re.search(r"<!-- repo-template-head:([a-f0-9]{40}) -->", pr.get("body", ""))
    bot = os.environ.get("MAINTENANCE_BOT_LOGIN", "")
    slug = bot.removesuffix("[bot]")
    if (
        not expected
        or not bot
        or pr.get("author", {}).get("login") not in {bot, f"app/{slug}"}
        or not merge_ready(
            {**pr, "mergeStateStatus": "CLEAN"} if pr.get("mergeStateStatus") == "BEHIND" else pr,
            expected.group(1),
        )
    ):
        raise ValueError(
            "maintenance PR is awaiting successful checks/review; leaving it unchanged"
        )
    checks = json.loads(
        run("gh", "api", f"repos/{repository}/commits/{pr['headRefOid']}/check-runs")
    )
    if not any(
        c.get("name") == "maintenance-admission"
        and c.get("head_sha") == pr["headRefOid"]
        and c.get("external_id") == pr["headRefOid"]
        and c.get("conclusion") == "success"
        and c.get("app", {}).get("slug") == slug
        for c in checks.get("check_runs", [])
    ):
        raise ValueError(
            "PR head has no matching App-issued admission evidence; rerun candidate evaluation"
        )
    if pr.get("mergeStateStatus") == "BEHIND":
        return {**pr, "number": number}
    run(
        "gh",
        "pr",
        "merge",
        number,
        "--repo",
        repository,
        "--squash",
        "--match-head-commit",
        pr["headRefOid"],
        "--delete-branch",
    )
    return True


def main() -> None:
    try:
        action = sys.argv[1]
        if action == "prepare":
            prepare(Path(sys.argv[2]), Path(sys.argv[3]))
        elif action == "publish":
            repository = os.environ["GITHUB_REPOSITORY"]
            activation(repository)
            existing = merge_existing(repository)
            if isinstance(existing, dict):
                publish(Path(sys.argv[2]), repository, refresh=existing)
            elif not existing:
                publish(Path(sys.argv[2]), repository)
        elif action == "merge":
            activation(os.environ["GITHUB_REPOSITORY"])
            merge_existing(os.environ["GITHUB_REPOSITORY"])
        else:
            raise ValueError("expected prepare, publish or merge")
    except (ValueError, OSError, KeyError) as exc:
        print(f"maintenance: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
