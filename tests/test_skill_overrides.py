from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from repo_template.model import Result
from repo_template.skillfile import (
    field_count,
    field_lines,
    read_fields,
    restore_field,
    set_field,
)
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
    (root / ".agents/claude-settings.json").write_text('{"portable": {}, "defaults": {}}\n')
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


@pytest.mark.parametrize(
    "fields",
    [{"description": "a --- b"}, {"bad key": "x"}, {"description: x\nhooks": "x"}],
)
def test_overrides_that_would_break_the_frontmatter_are_rejected(
    tmp_path: Path, fields: dict[str, str]
) -> None:
    """Claude Code ends the frontmatter at the first "---", even inside a quoted value."""
    standards = _standards(tmp_path / "standards", {"rag": {"frontmatter": fields}})

    with pytest.raises(ValueError, match="can't set"):
        apply_skill_overrides(standards, Result(standards), check=True)


lines = st.lists(
    st.tuples(
        st.text(alphabet="ab: \t\u2028\x0c\x85", max_size=6),
        st.sampled_from(["\n", "\r\n", "\r"]),
    ),
    max_size=5,
).map(lambda pairs: "".join(text + end for text, end in pairs))


@given(
    before=lines,
    value=st.text(max_size=20),
    after=lines,
    body=lines,
    ending=st.sampled_from(["\n", "\r\n"]),
)
def test_a_field_set_then_restored_gives_back_the_file(
    before: str, value: str, after: str, body: str, ending: str
) -> None:
    """The override round trip: whatever the layout, putting the recorded field back restores
    the file byte for byte, and setting it again is stable."""
    text = f"---{ending}name: s{ending}{before}description: old{ending}{after}---{ending}{body}"
    try:
        raw = field_lines(text, "description")
    except ValueError:
        return  # not a frontmatter skillfile can find (a stray "---" line)
    if field_count(text, "description") != 1:
        return
    changed = set_field(text, "description", value)

    assert read_fields(changed)["description"] == value
    assert restore_field(changed, "description", raw) == text
    assert set_field(changed, "description", value) == changed


def test_set_field_handles_windows_line_endings() -> None:
    crlf = SKILL.replace("\n", "\r\n")

    updated = set_field(crlf, "description", "Short.")

    assert read_fields(updated)["description"] == "Short."
    assert '\r\ndescription: "Short."\r\n' in updated
    assert "\n" not in updated.replace("\r\n", "")


def test_an_unusable_override_is_reported_without_stopping_the_others(tmp_path: Path) -> None:
    agents = tmp_path / ".agents"
    for name, text in {"broken": "no frontmatter\n", "rag": SKILL}.items():
        (agents / "skills" / name).mkdir(parents=True)
        (agents / "skills" / name / "SKILL.md").write_text(text)
    overrides = {
        name: {"why": "test", "frontmatter": {"description": "Short."}}
        for name in ("broken", "rag")
    }
    (agents / "skill-overrides.json").write_text(json.dumps(overrides))
    result = Result(tmp_path)

    apply_skill_overrides(tmp_path, result, check=False)

    assert len(result.errors) == 1 and "'broken'" in result.errors[0]
    assert read_fields((agents / "skills/rag/SKILL.md").read_text())["description"] == "Short."


def test_overrides_keep_a_skill_files_own_line_endings(tmp_path: Path) -> None:
    agents = tmp_path / ".agents"
    skill = agents / "skills/rag/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_bytes(SKILL.replace("\n", "\r\n").encode())
    overrides = {"rag": {"why": "test", "frontmatter": {"description": "Short."}}}
    (agents / "skill-overrides.json").write_text(json.dumps(overrides))

    apply_skill_overrides(tmp_path, Result(tmp_path), check=False)

    data = skill.read_bytes()
    assert b'description: "Short."\r\n' in data
    assert b"\n" not in data.replace(b"\r\n", b"")
