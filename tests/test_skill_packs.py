from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_template.model import Result
from repo_template.repository import create_repository, update_repository
from repo_template.scaffold import new_project, skill_packs
from repo_template.standards import sync_globals, sync_project_packs


def _catalog(root: Path) -> Path:
    """A standards repository whose .agents holds two pack skills (in packs/) and one global
    skill (in skills/)."""
    agents = root / ".agents"
    for name in ("core", "lc-one", "lc-two"):
        skill = agents / ("skills" if name == "core" else "packs") / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n")
    (agents / "skill-packs.json").write_text(
        json.dumps({"lc": {"description": "LangChain", "skills": ["lc-one", "lc-two"]}})
    )
    (root / ".agents/claude-settings.json").write_text('{"portable": {}, "defaults": {}}\n')
    return agents


def _repository(root: Path) -> Path:
    new_project(root, name=root.name, description="Sample.", python_version="3.12")
    return root


def test_globals_links_only_skills_outside_packs(tmp_path: Path) -> None:
    standards = tmp_path / "standards"
    _catalog(standards)
    home = tmp_path / "home"
    (home / ".claude/skills").mkdir(parents=True)
    (home / ".claude/skills/lc-one").symlink_to(standards / ".agents/skills/lc-one")

    result = sync_globals(standards, home=home)

    assert sorted(os.listdir(home / ".claude/skills")) == ["core"]
    assert sorted(os.listdir(standards / ".claude/skills")) == ["core"]
    assert str(home / ".claude/skills/lc-one") in result.removed


def test_globals_reports_a_pack_listing_a_missing_skill(tmp_path: Path) -> None:
    standards = tmp_path / "standards"
    agents = _catalog(standards)
    (agents / "skill-packs.json").write_text(json.dumps({"lc": {"skills": ["lc-one", "gone"]}}))

    result = sync_globals(standards, home=tmp_path / "home", check=True)

    assert any("'gone'" in error for error in result.errors)


def test_update_with_a_pack_links_it_and_records_it(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")

    planned = update_repository(
        root, check=True, hooks=False, lock=False, packs=["lc"], agents_dir=agents
    )
    applied = update_repository(root, hooks=False, lock=False, packs=["lc"], agents_dir=agents)

    expected = [
        ".claude/skills/lc-one",
        ".claude/skills/lc-two",
        ".agents/skills/lc-one",  # for Codex, which reads a repository's .agents/skills
        ".agents/skills/lc-two",
    ]
    assert planned.created == expected
    assert applied.created == expected
    assert os.readlink(root / ".claude/skills/lc-one") == str(agents / "packs/lc-one")
    assert os.readlink(root / ".agents/skills/lc-one") == str(agents / "packs/lc-one")
    assert skill_packs(root) == ["lc"]
    current = update_repository(root, check=True, hooks=False, lock=False, agents_dir=agents)
    assert not current.needs_attention


def test_dropping_a_pack_removes_only_its_links(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    update_repository(root, hooks=False, lock=False, packs=["lc"], agents_dir=agents)
    own_skill = root / ".claude/skills/project-only"
    own_skill.mkdir()
    manifest_path = root / ".repo-template.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["skill_packs"]
    manifest_path.write_text(json.dumps(manifest))

    result = update_repository(root, hooks=False, lock=False, agents_dir=agents)

    assert result.removed == [
        ".claude/skills/lc-one",
        ".claude/skills/lc-two",
        ".agents/skills/lc-one",
        ".agents/skills/lc-two",
    ]
    assert sorted(os.listdir(root / ".claude/skills")) == ["project-only"]


def test_a_skill_shared_by_two_packs_stays_when_one_is_dropped(tmp_path: Path) -> None:
    """frontend-design serves gradio, react and openwebui."""
    agents = _catalog(tmp_path / "standards")
    packs = json.loads((agents / "skill-packs.json").read_text())
    packs["ui"] = {"description": "UI", "skills": ["lc-two"]}
    (agents / "skill-packs.json").write_text(json.dumps(packs))
    root = _repository(tmp_path / "service")
    update_repository(root, hooks=False, lock=False, packs=["lc", "ui"], agents_dir=agents)
    manifest_path = root / ".repo-template.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["skill_packs"] = ["ui"]
    manifest_path.write_text(json.dumps(manifest))

    result = update_repository(root, hooks=False, lock=False, agents_dir=agents)

    assert result.removed == [".claude/skills/lc-one", ".agents/skills/lc-one"]
    assert sorted(os.listdir(root / ".claude/skills")) == ["lc-two"]
    assert sorted(os.listdir(root / ".agents/skills")) == ["lc-two"]


def test_links_from_before_pack_skills_moved_are_repointed(tmp_path: Path) -> None:
    """Pack skills used to live in .agents/skills; a repository's old links get the new home."""
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    update_repository(root, hooks=False, lock=False, packs=["lc"], agents_dir=agents)
    (root / ".claude/skills/lc-one").unlink()
    (root / ".claude/skills/lc-one").symlink_to(agents / "skills/lc-one")  # dangling now
    (root / ".agents/skills/lc-two").unlink()

    result = update_repository(root, hooks=False, lock=False, agents_dir=agents)

    assert result.updated == [".claude/skills/lc-one"]
    assert result.created == [".agents/skills/lc-two"]
    assert os.readlink(root / ".claude/skills/lc-one") == str(agents / "packs/lc-one")


def test_the_catalog_is_never_linked_into_itself(tmp_path: Path) -> None:
    """In the standards repository, .agents is the catalog: only .claude/skills gets links."""
    from repo_template.model import Result
    from repo_template.standards import sync_project_packs

    agents = _catalog(tmp_path / "standards")
    result = Result(tmp_path / "standards")

    sync_project_packs(tmp_path / "standards", ["lc"], result, check=False, agents_dir=agents)

    assert result.created == [".claude/skills/lc-one", ".claude/skills/lc-two"]
    assert not (agents / "skills/lc-one").exists()


def test_unknown_pack_is_rejected_before_anything_changes(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    before = (root / ".repo-template.json").read_text()

    with pytest.raises(ValueError, match=r"unknown skill pack: nope \(the packs: lc"):
        update_repository(root, hooks=False, lock=False, packs=["nope"], agents_dir=agents)
    assert (root / ".repo-template.json").read_text() == before


def test_update_never_touches_a_standards_repository_mirror(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    mirror = root / ".claude/skills"
    mirror.mkdir(parents=True)
    (mirror / "core").symlink_to(Path("../../.agents/skills/core"))

    result = update_repository(root, hooks=False, lock=False, agents_dir=agents)

    assert result.removed == []
    assert (mirror / "core").is_symlink()


def test_new_repository_can_start_with_a_pack(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")

    result = create_repository(
        tmp_path / "agent",
        name="agent",
        description="Agent.",
        python_version="3.12",
        git=False,
        lock=False,
        packs=["lc"],
        agents_dir=agents,
    )

    assert ".claude/skills/lc-one" in result.created
    assert skill_packs(result.root) == ["lc"]


def test_a_pack_the_catalog_no_longer_defines_is_reported_and_its_links_kept(
    tmp_path: Path,
) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    update_repository(root, hooks=False, lock=False, packs=["lc"], agents_dir=agents)
    (agents / "skill-packs.json").write_text(json.dumps({"renamed": {"skills": ["lc-one"]}}))

    result = update_repository(root, hooks=False, lock=False, agents_dir=agents)

    assert any("'lc'" in error and "left in place" in error for error in result.errors)
    assert result.removed == []
    assert sorted(os.listdir(root / ".claude/skills")) == ["lc-one", "lc-two"]


def test_check_reports_the_manifest_change_a_new_pack_would_make(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")

    planned = update_repository(
        root, check=True, hooks=False, lock=False, packs=["lc"], agents_dir=agents
    )

    assert ".repo-template.json" in planned.updated
    assert skill_packs(root) == []


def _sync(root: Path, agents: Path, *, check: bool) -> Result:
    result = Result(root)
    sync_project_packs(root, ["lc"], result, check=check, agents_dir=agents)
    return result


def test_a_link_this_tool_did_not_make_is_kept(tmp_path: Path) -> None:
    """`npx skills add` leaves .agents/skills/<name> as a folder and .claude/skills/<name> as a
    relative link to it: both tools keep that copy."""
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    (root / ".agents/skills/lc-one").mkdir(parents=True)
    (root / ".agents/skills/lc-one/SKILL.md").write_text("---\nname: lc-one\n---\n")
    (root / ".claude/skills").mkdir(parents=True)
    (root / ".claude/skills/lc-one").symlink_to(Path("../../.agents/skills/lc-one"))
    (root / ".agents/skills/lc-two").symlink_to(tmp_path / "mine/lc-two")

    planned = _sync(root, agents, check=True)
    applied = _sync(root, agents, check=False)

    assert (
        planned.preserved
        == applied.preserved
        == [
            ".claude/skills/lc-one (a link this tool didn't make; remove it so the skill can be "
            "linked)",
            ".agents/skills/lc-one (not a link; remove it so the skill can be linked)",
            ".agents/skills/lc-two (a link this tool didn't make; remove it so the skill can be "
            "linked)",
        ]
    )
    assert planned.created == applied.created == [".claude/skills/lc-two"]
    assert os.readlink(root / ".claude/skills/lc-one") == "../../.agents/skills/lc-one"
    assert os.readlink(root / ".agents/skills/lc-two") == str(tmp_path / "mine/lc-two")


@pytest.mark.parametrize("kind", ["dangling link", "file"])
def test_a_repository_whose_agents_is_not_a_folder_still_converges(
    tmp_path: Path, kind: str
) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    if kind == "file":
        (root / ".agents").write_text("")
    else:
        (root / ".agents").symlink_to(tmp_path / "moved/.agents")

    planned = _sync(root, agents, check=True)
    applied = _sync(root, agents, check=False)

    assert planned.preserved == applied.preserved == [".agents (not a folder; skill links skipped)"]
    assert planned.created == applied.created == [".claude/skills/lc-one", ".claude/skills/lc-two"]
    assert _sync(root, agents, check=True).created == []


def test_pack_links_never_go_into_the_catalog(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    (root / ".agents").mkdir()
    (root / ".agents/skills").symlink_to(agents / "skills", target_is_directory=True)

    result = _sync(root, agents, check=False)

    assert result.preserved == [
        ".agents/skills (the skill catalog itself, so pack skills aren't linked there; make "
        ".agents a folder of this repository's own)"
    ]
    assert sorted(os.listdir(agents / "skills")) == ["core"]
    (root / ".agents/skills").unlink()
    (root / ".agents").rmdir()
    (root / ".agents").symlink_to(agents, target_is_directory=True)
    assert _sync(root, agents, check=True).preserved == result.preserved  # never "current"


def test_pack_links_never_go_outside_the_repository(tmp_path: Path) -> None:
    """Two repositories sharing one folder would undo each other's links."""
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    shared = tmp_path / "shared"
    shared.mkdir()
    (root / ".agents").symlink_to(shared, target_is_directory=True)

    result = _sync(root, agents, check=False)

    assert result.preserved == [
        ".agents/skills (resolves outside this repository; pack skills aren't linked there)"
    ]
    assert list(shared.iterdir()) == []


def test_a_checkout_of_the_standards_repository_gets_no_links_in_its_catalog(
    tmp_path: Path,
) -> None:
    """A second checkout (a worktree) has a catalog of its own in .agents/skills."""
    agents = _catalog(tmp_path / "standards")
    checkout = tmp_path / "worktree"
    shutil.copytree(agents.parent, checkout)

    result = _sync(checkout, agents, check=False)

    assert result.created == [".claude/skills/lc-one", ".claude/skills/lc-two"]
    assert sorted(os.listdir(checkout / ".agents/skills")) == ["core"]


def test_a_link_git_would_not_ignore_is_not_made(tmp_path: Path) -> None:
    """A repository that commits .agents/skills: a link there, to this machine's catalog,
    would be committed by the next `git add -A`."""
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "core.excludesFile", os.devnull], check=True)
    with (root / ".gitignore").open("a") as handle:
        handle.write("!.agents/\n!.agents/skills/\n")

    planned = _sync(root, agents, check=True)
    applied = _sync(root, agents, check=False)

    expected = [
        f".agents/skills/{name} (Git wouldn't ignore this link; ignore it so the skill can be "
        f"linked)"
        for name in ("lc-one", "lc-two")
    ]
    assert planned.preserved == applied.preserved == expected
    assert planned.created == applied.created == [".claude/skills/lc-one", ".claude/skills/lc-two"]
    assert not (root / ".agents/skills").exists()


def test_one_folder_shared_by_both_tools_is_linked_once(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    (root / ".agents/skills").mkdir(parents=True)
    (root / ".claude").mkdir()
    (root / ".claude/skills").symlink_to(Path("../.agents/skills"), target_is_directory=True)

    planned = _sync(root, agents, check=True)
    applied = _sync(root, agents, check=False)

    assert planned.created == applied.created == [".claude/skills/lc-one", ".claude/skills/lc-two"]
    assert not _sync(root, agents, check=True).needs_attention


def test_a_relative_catalog_path_still_makes_working_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    monkeypatch.chdir(tmp_path)

    _sync(root, Path("standards/.agents"), check=False)

    assert (root / ".claude/skills/lc-one/SKILL.md").is_file()


def test_a_catalog_not_yet_moved_is_linked_from_skills(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    shutil.move(agents / "packs/lc-one", agents / "skills/lc-one")
    root = _repository(tmp_path / "service")

    _sync(root, agents, check=False)

    assert os.readlink(root / ".claude/skills/lc-one") == str(agents / "skills/lc-one")
    assert os.readlink(root / ".claude/skills/lc-two") == str(agents / "packs/lc-two")


def test_links_from_before_the_move_go_when_their_pack_is_dropped(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _repository(tmp_path / "service")
    update_repository(root, hooks=False, lock=False, packs=["lc"], agents_dir=agents)
    for folder in (".claude/skills", ".agents/skills"):
        (root / folder / "lc-one").unlink()
        (root / folder / "lc-one").symlink_to(agents / "skills/lc-one")  # made by 0.4.2

    manifest_path = root / ".repo-template.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["skill_packs"]
    manifest_path.write_text(json.dumps(manifest))

    result = update_repository(root, hooks=False, lock=False, agents_dir=agents)

    assert ".claude/skills/lc-one" in result.removed and ".agents/skills/lc-one" in result.removed
    assert os.listdir(root / ".claude/skills") == os.listdir(root / ".agents/skills") == []
