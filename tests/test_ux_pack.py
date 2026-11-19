"""The UX pack is usable through repository links without a native plugin install."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from repo_template.model import Result
from repo_template.standards import load_skill_packs, sync_project_packs

ROOT = Path(__file__).resolve().parents[1]


def test_ux_resources_and_search_work_from_a_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    agents = ROOT / ".agents"
    result = Result(project)
    sync_project_packs(
        project, ["ux"], result, check=False, agents_dir=agents, ignored=lambda paths: set(paths)
    )
    assert not result.errors
    for name in load_skill_packs(agents)["ux"]:
        for client in (".agents", ".claude"):
            assert (project / client / "skills" / name / "SKILL.md").is_file()
    assert (project / ".agents/skills/impeccable/reference/operate.md").is_file()
    script = project / ".agents/skills/ui-ux-pro-max/scripts/search.py"
    searched = subprocess.run(
        [sys.executable, str(script), "keyboard focus modal", "--domain", "ux"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert "focus" in searched.stdout.lower()
    assert "keyboard" in searched.stdout.lower()
    assert not (project / "design-system").exists()

    checked = Result(project)
    sync_project_packs(
        project,
        ["ux"],
        checked,
        check=True,
        agents_dir=agents,
        ignored=lambda paths: set(paths),
    )
    assert not checked.needs_attention
