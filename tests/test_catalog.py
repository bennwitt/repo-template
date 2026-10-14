"""Checks over this repository's own skill catalog, so a bad skill fails CI, not a session."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from repo_template.catalog import DESCRIPTION_LIMIT
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


def test_every_pack_lists_catalog_skills() -> None:
    """A skill may be in several packs (frontend-design serves gradio, react and openwebui)."""
    members = [name for skills in PACKS.values() for name in skills]

    assert set(members) <= set(SKILLS), set(members) - set(SKILLS)


def test_descriptions_this_repository_writes_fit_the_budget() -> None:
    """Every description loads on every turn, in Claude Code and in Codex (which sees the whole
    catalog). Overrides and local skills, which this repository writes, stay short."""
    overrides = json.loads((ROOT / ".agents/skill-overrides.json").read_text())
    local = json.loads((ROOT / ".agents/skill-sources.json").read_text())["local"]
    for name in sorted(set(overrides) | set(local)):
        description = read_fields((ROOT / ".agents/skills" / name / "SKILL.md").read_text())[
            "description"
        ]
        assert len(description) <= DESCRIPTION_LIMIT, f"{name}: {len(description)} characters"


@pytest.mark.parametrize("name", sorted(p.name for p in (ROOT / ".agents").glob("*.json")))
def test_every_catalog_data_file_is_committed(name: str) -> None:
    """`/.agents/*` is ignored with re-includes; a new data file must be re-included too."""
    ignored = subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", "-q", f".agents/{name}"], check=False
    )
    assert ignored.returncode == 1, f".agents/{name} is ignored by .gitignore"


@pytest.mark.parametrize(
    ("path", "ignored"),
    [
        (".agents/licenses/o_r__LICENSE.txt", False),
        (".agents/licenses/.gitattributes", False),
        (".agents/skills/x/scripts/run.py", False),
        (".agents/skills/x/scripts/__pycache__/run.cpython-311.pyc", True),
        (".agents/skills/x/.DS_Store", True),
        (".agents/skills/x/.ruff_cache/0.1/a", True),
    ],
)
def test_catalog_files_are_committed_and_caches_are_not(path: str, ignored: bool) -> None:
    """`git add .agents` must stage license texts and skills, never the caches a skill's scripts
    leave when they run in place."""
    done = subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", "-q", "--no-index", path], check=False
    )
    assert done.returncode == (0 if ignored else 1), path


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
