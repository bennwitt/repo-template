"""The pragmatic-design pack links the 72% plan skill, its references and the pre-mortem."""

from __future__ import annotations

from pathlib import Path

from repo_template.model import Result
from repo_template.standards import load_skill_packs, sync_project_packs

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ("principles.md", "plan-template.md", "one-way-doors.md", "skip-list.md")


def test_the_plan_skill_and_its_references_land_in_a_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    agents = ROOT / ".agents"
    assert load_skill_packs(agents)["pragmatic-design"] == ["seventy-two-percent-plan", "the-fool"]

    result = Result(project)
    sync_project_packs(
        project,
        ["pragmatic-design"],
        result,
        check=False,
        agents_dir=agents,
        ignored=lambda paths: set(paths),
    )
    assert not result.errors
    for client in (".agents", ".claude"):
        skills = project / client / "skills"
        assert (skills / "the-fool/SKILL.md").is_file()
        plan = skills / "seventy-two-percent-plan"
        assert (plan / "SKILL.md").is_file()
        for name in REFERENCES:
            assert (plan / "references" / name).is_file(), name
    body = (project / ".claude/skills/seventy-two-percent-plan/SKILL.md").read_text()
    for name in REFERENCES:
        assert f"references/{name}" in body, f"SKILL.md does not point at {name}"

    checked = Result(project)
    sync_project_packs(
        project,
        ["pragmatic-design"],
        checked,
        check=True,
        agents_dir=agents,
        ignored=lambda paths: set(paths),
    )
    assert not checked.needs_attention
