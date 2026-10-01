"""This repository is the first consumer of its own baseline, so drift fails CI here."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from repo_template.model import ProjectContext
from repo_template.repository import update_repository
from repo_template.templates import project_files

ROOT = Path(__file__).resolve().parents[1]


def _baseline() -> dict[str, str]:
    context = ProjectContext("repo-template", "repo_template", "Standards.", "3.11")
    return {spec.relative_path: spec.content for spec in project_files(context)}


def test_this_repository_meets_its_own_baseline() -> None:
    """Dependabot updates land here first; this fails until templates.py catches up."""
    result = update_repository(ROOT, check=True, hooks=False)

    assert not result.needs_attention, (
        "this repository has drifted from its baseline; copy the newer version into "
        f"templates.py or run `uv run repo-template update .`: created={result.created} "
        f"updated={result.updated} preserved={result.preserved}"
    )


def test_baseline_pins_match_this_repository() -> None:
    ours = tomllib.loads((ROOT / "pyproject.toml").read_text())
    baseline = tomllib.loads(_baseline()["pyproject.toml"])

    assert baseline["build-system"]["requires"] == ours["build-system"]["requires"]
    assert set(ours["dependency-groups"]["dev"]) <= set(baseline["dependency-groups"]["dev"])


def test_workflow_actions_are_pinned_to_a_commit() -> None:
    """Tags can move or disappear (setup-uv stopped publishing a floating v10); SHAs can't."""
    uses = re.findall(r"uses:\s*(\S+)(.*)", _baseline()[".github/workflows/ci.yml"])

    assert uses
    for action, comment in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action), action
        assert re.fullmatch(r"\s*# v\d+(\.\d+)*", comment), f"{action} needs a # vX.Y.Z comment"
