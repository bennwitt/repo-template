from __future__ import annotations

import json

import pytest

from repo_template.policies import (
    GITIGNORE_END,
    GITIGNORE_START,
    POLICIES,
    Decision,
    Outcome,
    digest,
    merge_marked_block,
)

DESIRED = "standard\n"
EDITED = "edited\n"


@pytest.mark.parametrize(
    ("existing", "recorded", "expected"),
    [
        (None, None, Decision(Outcome.CREATE, DESIRED)),
        (DESIRED, None, Decision(Outcome.UNCHANGED, DESIRED)),
        ("old standard\n", digest("old standard\n"), Decision(Outcome.UPGRADE, DESIRED)),
        (EDITED, digest("old standard\n"), Decision(Outcome.PRESERVE)),
        (EDITED, None, Decision(Outcome.PRESERVE)),
    ],
    ids=["missing", "current", "unedited-since-generated", "edited", "never-recorded"],
)
def test_managed_upgrades_only_unedited_files(
    existing: str | None, recorded: str | None, expected: Decision
) -> None:
    assert POLICIES["managed"].decide(existing, DESIRED, recorded) == expected


def test_managed_records_a_hash_only_when_current() -> None:
    assert POLICIES["managed"].record(DESIRED, DESIRED) == digest(DESIRED)
    assert POLICIES["managed"].record(EDITED, DESIRED) is None


def test_seed_is_written_once_then_left_alone() -> None:
    seed = POLICIES["seed"]

    assert seed.decide(None, DESIRED, None) == Decision(Outcome.CREATE, DESIRED)
    assert seed.decide(EDITED, DESIRED, None).outcome is Outcome.UNCHANGED
    assert seed.record(DESIRED, DESIRED) is None


def test_gitignore_block_keeps_project_rules_and_replaces_only_its_block() -> None:
    gitignore = POLICIES["gitignore"]
    created = gitignore.decide(None, "*.pyc\n", None)
    project = "local/\n\n" + created.content

    upgraded = gitignore.decide(project, "*.pyc\n.venv/\n", None)

    assert created.content == f"{GITIGNORE_START}\n*.pyc\n{GITIGNORE_END}\n"
    assert upgraded.outcome is Outcome.UPGRADE
    assert upgraded.content == f"local/\n\n{GITIGNORE_START}\n*.pyc\n.venv/\n{GITIGNORE_END}\n"
    assert gitignore.decide(upgraded.content, "*.pyc\n.venv/\n", None).outcome is Outcome.UNCHANGED


def test_marked_block_content_is_inserted_literally() -> None:
    merged = merge_marked_block("[start]\nold\n[end]\n", r"\1 and \g<0>", "[start]", "[end]")

    assert merged == "[start]\n\\1 and \\g<0>\n[end]\n"


def test_json_merge_adds_without_removing_and_preserves_invalid_json() -> None:
    merge = POLICIES["json_merge"]
    desired = '{"recommendations": ["a", "b"], "new": true}'

    decision = merge.decide('{"recommendations": ["mine", "a"]}', desired, None)

    assert json.loads(decision.content) == {"recommendations": ["mine", "a", "b"], "new": True}
    assert merge.decide("{not json", desired, None) == Decision(
        Outcome.PRESERVE, note="invalid JSON"
    )


def test_toml_merge_preserves_invalid_toml() -> None:
    decision = POLICIES["toml_merge"].decide("[project\n", '[project]\nname = "x"\n', None)

    assert decision == Decision(Outcome.PRESERVE, note="invalid TOML")


def test_toml_merge_leaves_an_already_configured_tool_alone() -> None:
    existing = '[project]\nname = "x"\n\n[tool.ruff.lint]\nselect = ["F"]\n'
    desired = (
        '[project]\nname = "x"\n\n[tool.ruff]\nline-length = 100\n\n'
        '[tool.ruff.lint]\nselect = ["E", "F"]\n\n[tool.mypy]\nstrict = true\n'
    )

    merged = POLICIES["toml_merge"].decide(existing, desired, None).content

    assert "line-length" not in merged
    assert 'select = ["F"]' in merged
    assert "[tool.mypy]" in merged
