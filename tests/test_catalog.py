"""Checks over this repository's own skill catalog, so a bad skill fails CI, not a session."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from repo_template.model import Result
from repo_template.skillfile import read_fields
from repo_template.standards import (
    SKILL_MIRROR_TARGET,
    apply_skill_overrides,
    load_skill_packs,
    skill_names,
)

ROOT = Path(__file__).resolve().parents[1]
SKILLS = skill_names(ROOT)
PACKS = load_skill_packs(ROOT / ".agents")
NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


@pytest.mark.parametrize("name", SKILLS)
def test_skill_frontmatter_is_valid(name: str) -> None:
    fields = read_fields((ROOT / ".agents/skills" / name / "SKILL.md").read_text())

    assert fields.get("name") == name
    assert NAME.fullmatch(name) and len(name) <= 64
    description = fields.get("description", "")
    assert description, "description is required"
    assert len(description) <= 1024, f"description is {len(description)} characters"


def test_every_pack_lists_catalog_skills_and_no_skill_is_in_two_packs() -> None:
    members = [name for skills in PACKS.values() for name in skills]

    assert set(members) <= set(SKILLS), set(members) - set(SKILLS)
    assert len(members) == len(set(members))


def test_repository_mirror_matches_the_global_skills() -> None:
    mirror = ROOT / ".claude/skills"
    links = {entry.name: Path(os.readlink(entry)) for entry in mirror.iterdir()}
    in_packs = {name for skills in PACKS.values() for name in skills}

    assert links == {name: SKILL_MIRROR_TARGET / name for name in SKILLS if name not in in_packs}


def test_skill_overrides_are_applied() -> None:
    """After `npx skills update`, run `repo-template globals` to re-apply the overrides."""
    result = Result(ROOT)

    apply_skill_overrides(ROOT, result, check=True)

    assert result.errors == []
    assert result.updated == [], "run `uv run repo-template globals` to re-apply overrides"
