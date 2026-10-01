"""This repository uses the project baseline too, so Dependabot updates here must reach it."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from repo_template.model import ProjectContext
from repo_template.templates import project_files

ROOT = Path(__file__).resolve().parents[1]
SHARED_FILES = [
    ".ai/.gitignore",
    ".ai/receipt-policy.json",
    ".editorconfig",
    ".gitattributes",
    ".githooks/pre-commit",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/dependabot.yml",
    ".github/workflows/ci.yml",
]


def _baseline() -> dict[str, str]:
    context = ProjectContext("repo-template", "repo_template", "Standards.", "3.11")
    return {spec.relative_path: spec.content for spec in project_files(context)}


@pytest.mark.parametrize("path", SHARED_FILES)
def test_shared_file_matches_the_baseline(path: str) -> None:
    assert (ROOT / path).read_text() == _baseline()[path], (
        f"{path} differs from templates.py; copy the newer version into the other"
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
