from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_template.model import Result
from repo_template.skillfile import read_fields, set_field
from repo_template.standards import apply_skill_overrides, sync_globals

SKILL = """---
name: rag
description: >-
  INVOKE THIS SKILL when building ANY
  RAG system.
metadata:
  owner: upstream
---

# Body
"""


def test_set_field_replaces_a_folded_value_and_keeps_the_rest() -> None:
    updated = set_field(SKILL, "description", 'RAG with LangChain: "loaders", splitters.')

    assert read_fields(updated)["description"] == 'RAG with LangChain: "loaders", splitters.'
    assert read_fields(updated)["name"] == "rag"
    assert "  owner: upstream\n" in updated
    assert updated.endswith("---\n\n# Body\n")


def test_set_field_adds_a_missing_field_before_the_closing_marker() -> None:
    updated = set_field(SKILL, "disable-model-invocation", True)

    assert read_fields(updated)["disable-model-invocation"] == "true"
    assert updated.index("disable-model-invocation") < updated.index("---\n\n# Body")


def test_read_fields_unquotes_values() -> None:
    text = "---\nname: 'it''s'\ndescription: \"say \\\"hi\\\"\"\n---\n"

    assert read_fields(text) == {"name": "it's", "description": 'say "hi"'}


def _standards(root: Path, overrides: dict[str, object]) -> Path:
    skill = root / ".agents/skills/rag"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(SKILL)
    (root / ".agents/skill-overrides.json").write_text(json.dumps(overrides))
    (root / ".claude").mkdir()
    (root / ".claude/settings.json").write_text("{}\n")
    return root


def test_overrides_survive_an_upstream_update(tmp_path: Path) -> None:
    standards = _standards(
        tmp_path / "standards",
        {"rag": {"why": "too broad", "frontmatter": {"description": "LangChain RAG only."}}},
    )
    skill_md = standards / ".agents/skills/rag/SKILL.md"
    home = tmp_path / "home"

    planned = sync_globals(standards, home=home, check=True)
    sync_globals(standards, home=home)

    assert f"{skill_md} (override)" in planned.updated
    assert read_fields(skill_md.read_text())["description"] == "LangChain RAG only."
    assert not sync_globals(standards, home=home, check=True).needs_attention

    skill_md.write_text(SKILL)  # what `npx skills update` does
    sync_globals(standards, home=home)

    assert read_fields(skill_md.read_text())["description"] == "LangChain RAG only."


def test_override_for_a_missing_skill_is_an_error(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "standards", {"gone": {"frontmatter": {"description": "x"}}})
    result = Result(standards)

    apply_skill_overrides(standards, result, check=True)

    assert any("'gone'" in error for error in result.errors)


def test_malformed_overrides_are_rejected(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "standards", {"rag": {"description": "no frontmatter key"}})

    with pytest.raises(ValueError, match="frontmatter"):
        apply_skill_overrides(standards, Result(standards), check=True)
