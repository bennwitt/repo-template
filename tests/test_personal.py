"""Personal adoption: skill packs for one person in a repository nobody else sees change."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from repo_template import cli
from repo_template.mcp_globals import ClaudeCli
from repo_template.personal import EXCLUDE_LABEL, EXCLUDE_START
from repo_template.policies import merge_marked_block, remove_marked_block
from repo_template.repository import create_repository, update_repository
from repo_template.repository import local_claude as real_local_claude  # before conftest patches it
from repo_template.runner import Completed
from repo_template.scaffold import manifest_version, read_manifest

DOCS = {"scope": "pack", "url": "https://docs.example.com/mcp", "source": "s", "why": "w"}
GIT = ["git", "-c", "user.name=T", "-c", "user.email=t@example.com"]


class FakeClaude:
    """Claude Code's local scope for one checkout, in memory."""

    def __init__(self, path: Path, *, on_path: bool = True) -> None:
        self.path, self.on_path = path, on_path
        self.data: dict[str, Any] = {}
        self.calls: list[tuple[str, str]] = []

    def available(self) -> bool:
        return self.on_path

    def exists(self) -> bool:
        return True

    def servers(self) -> dict[str, Any]:
        return deepcopy(self.data)

    def add(self, name: str, entry: Mapping[str, Any]) -> Completed:
        self.calls.append(("add", name))
        if name in self.data:
            return Completed(1, "", f"MCP server {name} already exists in local config")
        self.data[name] = dict(entry)
        return Completed(0)

    def remove(self, name: str) -> Completed:
        self.calls.append(("remove", name))
        if name not in self.data:
            return Completed(1, "", "no such server")
        del self.data[name]
        return Completed(0)


def _catalog(root: Path) -> Path:
    agents = root / ".agents"
    for name in ("ts-one", "ts-two"):
        (agents / "packs" / name).mkdir(parents=True)
        (agents / "packs" / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
    packs = {
        "ts": {"description": "TS", "skills": ["ts-one"], "mcp": ["docs"]},
        "more": {"description": "More", "skills": ["ts-two"]},
    }
    (agents / "skill-packs.json").write_text(json.dumps(packs))
    (agents / "mcp-servers.json").write_text(json.dumps({"schema": 1, "servers": {"docs": DOCS}}))
    return agents


def _git(root: Path, *args: str) -> str:
    done = subprocess.run([*GIT, "-C", str(root), *args], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


def _team_repo(root: Path, files: Mapping[str, str] | None = None) -> Path:
    """A team's repository, everything committed, ignoring nothing this tool writes: no global
    excludes, and no .gitignore rule for .claude, .agents or .codex."""
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "core.excludesFile", os.devnull)
    (root / "package.json").write_text('{"name": "team"}\n')
    for name, text in (files or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "team")
    return root


def _status(root: Path) -> str:
    """What the team could see change: anything tracked or untracked that Git doesn't ignore."""
    return _git(root, "status", "--porcelain", "--untracked-files=all")


def _files(root: Path) -> dict[str, str]:
    """Every file and link outside .git, with its content or target, and the two in .git that
    personal adoption writes."""
    found: dict[str, str] = {}
    for folder, dirs, files in os.walk(root):
        here = Path(folder).relative_to(root)
        dirs[:] = [name for name in dirs if (here / name).parts != (".git",)]
        for name in [*files, *(d for d in dirs if (Path(folder) / d).is_symlink())]:
            path = Path(folder) / name
            found[str(here / name)] = (
                os.readlink(path) if path.is_symlink() else path.read_text(errors="replace")
            )
    for name in (".git/info/exclude", ".git/repo-template.json"):
        if (root / name).exists():
            found[name] = (root / name).read_text()
    return found


def _update(root: Path, agents: Path, claude: FakeClaude | None, home: Path, **kwargs: Any) -> Any:
    return update_repository(root, agents_dir=agents, claude=claude, home=home, **kwargs)


@pytest.fixture
def setup(tmp_path: Path) -> tuple[Path, Path, FakeClaude, Path]:
    agents = _catalog(tmp_path / "standards")
    root = _team_repo(tmp_path / "team")
    home = tmp_path / "home"
    return agents, root, FakeClaude(home / ".claude.json"), home


def test_adopting_changes_nothing_anyone_else_sees(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup

    planned = _update(root, agents, claude, home, check=True, packs=["ts"], personal=True)
    assert claude.calls == []  # check runs no claude command
    applied = _update(root, agents, claude, home, packs=["ts"], personal=True)

    assert planned.created == applied.created
    assert _status(root) == ""
    assert not (root / ".repo-template.json").exists() and not (root / ".mcp.json").exists()
    assert os.readlink(root / ".claude/skills/ts-one") == str(agents.absolute() / "packs/ts-one")
    assert (root / ".agents/skills/ts-one").is_symlink()
    assert "[mcp_servers.docs]" in (root / ".codex/config.toml").read_text()
    manifest = json.loads((root / ".git/repo-template.json").read_text())
    assert manifest["profile"] == "personal" and manifest["skill_packs"] == ["ts"]
    assert set(manifest) == {"schema", "template_version", "profile", "skill_packs"}
    exclude = (root / ".git/info/exclude").read_text()
    assert (
        f"{EXCLUDE_START}\n"
        "/.agents/skills/ts-one\n!/.agents/skills/ts-one/\n"
        "/.claude/skills/ts-one\n!/.claude/skills/ts-one/\n"
        "/.codex/config.toml\n/.codex/.config.toml.repo-template-tmp\n"
    ) in exclude
    assert claude.calls == [("add", "docs")] and claude.data["docs"]["url"] == DOCS["url"]
    labels = [".git/repo-template.json", EXCLUDE_LABEL, ".claude/skills/ts-one"]
    assert set(labels) <= set(applied.created)
    again = _update(root, agents, claude, home, check=True)
    assert not again.needs_attention, again


def test_a_second_run_with_no_flag_stays_personal(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts"], personal=True)
    before = _files(root)

    result = _update(root, agents, claude, home)
    assert not result.needs_attention and _files(root) == before
    added = _update(root, agents, claude, home, packs=["more"])

    assert ".claude/skills/ts-two" in added.created and _status(root) == ""
    assert not (root / ".repo-template.json").exists() and not (root / ".mcp.json").exists()
    assert not (root / "pyproject.toml").exists() and not (root / ".githooks").exists()
    assert read_manifest(root)["skill_packs"] == ["more", "ts"]
    assert manifest_version(root) == read_manifest(root)["template_version"]


def test_check_reports_what_update_does_when_the_team_un_ignores_skill_links(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    (root / ".gitignore").write_text("!.claude/skills/*\n")  # a .gitignore beats info/exclude
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-q", "-m", "un-ignore")

    planned = _update(root, agents, claude, home, check=True, packs=["ts"], personal=True)
    applied = _update(root, agents, claude, home, packs=["ts"], personal=True)
    again = _update(root, agents, claude, home, check=True)

    refused = (
        ".claude/skills/ts-one (Git wouldn't ignore this link; ignore it so the skill can be "
        "linked)"
    )
    assert planned.preserved == applied.preserved == again.preserved == [refused]
    assert planned.created == applied.created and not again.created and not again.updated
    assert not (root / ".claude/skills/ts-one").exists()
    assert (root / ".agents/skills/ts-one").is_symlink() and _status(root) == ""


def test_a_deleted_exclude_block_is_reported_and_put_back(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts"], personal=True)
    exclude = root / ".git/info/exclude"
    original = exclude.read_text()
    exclude.write_text(
        remove_marked_block(original, EXCLUDE_START, "# <<< repo-template personal packs")
    )
    assert _status(root) != ""  # the links show up

    planned = _update(root, agents, claude, home, check=True)
    _update(root, agents, claude, home)

    assert planned.created == [EXCLUDE_LABEL]
    assert exclude.read_text() == original and _status(root) == ""


def test_the_teams_own_skills_links_and_servers_are_left_alone(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    team_mcp = '{"mcpServers": {"docs": {"type": "http", "url": "https://team.example.com"}}}\n'
    root = _team_repo(
        tmp_path / "team",
        {".claude/skills/ts-one/SKILL.md": "---\nname: ts-one\n---\n", ".mcp.json": team_mcp},
    )
    (root / ".agents/skills").mkdir(parents=True)  # a tracked link that looks like this tool's
    (root / ".agents/skills/ts-one").symlink_to(agents.absolute() / "packs/ts-one")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "team link")
    home = tmp_path / "home"
    claude = FakeClaude(home / ".claude.json")

    result = _update(root, agents, claude, home, packs=["ts", "more"], personal=True)

    assert [n for n in result.notes if "has its own" in n] == [
        ".claude/skills/ts-one: the repository has its own; the pack's skill isn't linked there",
        ".agents/skills/ts-one: the repository has its own; the pack's skill isn't linked there",
    ]
    assert (
        ".mcp.json defines docs, so the pack's isn't added (approve the repository's in Claude "
        "Code to use it)"
    ) in result.notes
    assert claude.calls == [] and (root / ".mcp.json").read_text() == team_mcp
    exclude = (root / ".git/info/exclude").read_text()
    assert "/ts-one" not in exclude and "/.claude/skills/ts-two" in exclude
    assert _status(root) == ""

    manifest = json.loads((root / ".git/repo-template.json").read_text())
    manifest["skill_packs"] = []
    (root / ".git/repo-template.json").write_text(json.dumps(manifest))
    dropped = _update(root, agents, claude, home)

    assert (root / ".agents/skills/ts-one").is_symlink()  # tracked: never pruned
    assert (root / ".claude/skills/ts-one/SKILL.md").is_file()
    assert ".agents/skills/ts-one" not in dropped.removed and _status(root) == ""


def test_a_skills_folder_linked_to_the_other_gets_one_link(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _team_repo(tmp_path / "team", {".agents/skills/team/SKILL.md": "team\n"})
    (root / ".claude").mkdir()
    (root / ".claude/skills").symlink_to("../.agents/skills")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "one folder")
    home = tmp_path / "home"

    result = _update(
        root, agents, FakeClaude(home / ".claude.json"), home, packs=["ts"], personal=True
    )

    assert ".agents/skills/ts-one" not in result.created  # through .claude/skills, once
    assert (root / ".agents/skills/ts-one").is_symlink() and _status(root) == ""
    exclude = (root / ".git/info/exclude").read_text()
    assert "/.agents/skills/ts-one\n" in exclude and "/.claude/skills/ts-one" not in exclude


def test_links_of_an_undefined_pack_stay_listed(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts"], personal=True)
    definitions = json.loads((agents / "skill-packs.json").read_text())
    (agents / "skill-packs.json").write_text(json.dumps({"more": definitions["more"]}))

    result = _update(root, agents, claude, home)

    assert any("'ts' is listed in the repository's manifest" in e for e in result.errors)
    assert (root / ".claude/skills/ts-one").is_symlink() and _status(root) == ""
    assert "/.claude/skills/ts-one" in (root / ".git/info/exclude").read_text()


def test_removing_every_pack_leaves_the_repository_as_it_was(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    (root / ".git/info").mkdir(exist_ok=True)
    (root / ".git/info/exclude").write_text("# mine\n*.log\n")
    before = _files(root)
    _update(root, agents, claude, home, packs=["ts"], personal=True)
    manifest = json.loads((root / ".git/repo-template.json").read_text())
    manifest["skill_packs"] = []
    (root / ".git/repo-template.json").write_text(json.dumps(manifest))

    planned = _update(root, agents, claude, home, check=True)
    removed = _update(root, agents, claude, home)

    assert planned.removed == removed.removed
    assert {EXCLUDE_LABEL, ".claude/skills/ts-one", ".codex/config.toml"} <= set(removed.removed)
    assert claude.data == {} and claude.calls[-1] == ("remove", "docs")
    after = _files(root)
    del after[".git/repo-template.json"]
    assert after == before and not (root / ".codex").exists()
    assert not _update(root, agents, claude, home, check=True).needs_attention


def test_local_servers_kept_by_hand_and_a_moved_checkout(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts"], personal=True)
    claude.data["docs"]["url"] = "https://mine.example.com/mcp"

    first = _update(root, agents, claude, home)
    second = _update(root, agents, claude, home)

    assert any("docs (configured by hand; kept)" in item for item in first.preserved)
    assert second.preserved == [] and claude.calls == [("add", "docs")]

    moved = root.with_name("moved")
    shutil.copytree(root, moved, symlinks=True)
    other = FakeClaude(home / ".claude.json")  # local scope is keyed by the checkout's path
    result = _update(moved, agents, other, home)

    assert other.calls == [("add", "docs")] and any("moved" in item for item in result.created)


def test_without_claude_the_links_and_codex_are_still_made(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, _, home = setup
    claude = FakeClaude(home / ".claude.json", on_path=False)

    result = _update(root, agents, claude, home, packs=["ts"], personal=True)

    assert "Claude Code's local-scope MCP servers: skipped (no `claude` on PATH)" in result.notes
    assert (root / ".claude/skills/ts-one").is_symlink() and (root / ".codex/config.toml").is_file()
    assert _status(root) == ""


def test_git_variables_from_a_hook_dont_point_it_at_another_repository(
    setup: tuple[Path, Path, FakeClaude, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents, root, claude, home = setup
    elsewhere = _team_repo(  # Git would answer for this one: it tracks a skill of that name
        tmp_path / "elsewhere", {".claude/skills/ts-one/SKILL.md": "theirs\n"}
    )
    monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(elsewhere))

    _update(root, agents, claude, home, packs=["ts"], personal=True)

    monkeypatch.delenv("GIT_DIR")
    monkeypatch.delenv("GIT_WORK_TREE")
    assert _status(root) == "" and _status(elsewhere) == ""
    assert (root / ".claude/skills/ts-one").is_symlink()
    assert "/.claude/skills/ts-one" in (root / ".git/info/exclude").read_text()


def _worktree(root: Path, tmp_path: Path) -> Path:
    _git(root, "worktree", "add", "-q", str(tmp_path / "linked"))
    return tmp_path / "linked"


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("team manifest", "adopts this repository for everyone"),
        ("team manifest says personal", "says it is personal"),
        ("both manifests", "has to go"),
        ("subfolder", "needs the top folder of a Git checkout"),
        ("linked worktree", "needs the top folder of a Git checkout"),
        ("not git", "needs the top folder of a Git checkout"),
        ("no pack", "--personal adopts a repository for its skill packs; name one with --pack"),
        ("with packs-only", "choose one"),
        ("packs-only later", "drop --packs-only"),
    ],
)
def test_a_refused_personal_adoption_writes_nothing(
    tmp_path: Path, case: str, message: str
) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _team_repo(tmp_path / "team", {"web/index.js": "x\n"})
    home = tmp_path / "home"
    claude = FakeClaude(home / ".claude.json")
    target, kwargs = root, {"packs": ["ts"], "personal": True}
    if case == "team manifest":
        (root / ".repo-template.json").write_text('{"schema": 1, "profile": "packs-only"}')
    elif case == "team manifest says personal":
        (root / ".repo-template.json").write_text('{"schema": 1, "profile": "personal"}')
        kwargs = {}
    elif case == "both manifests":
        _update(root, agents, claude, home, packs=["ts"], personal=True)
        (root / ".repo-template.json").write_text('{"schema": 1, "profile": "packs-only"}')
        kwargs = {}
    elif case == "subfolder":
        target = root / "web"
    elif case == "linked worktree":
        target = _worktree(root, tmp_path)
    elif case == "not git":
        target = tmp_path / "plain"
        target.mkdir()
    elif case == "no pack":
        kwargs = {"personal": True}
    elif case == "with packs-only":
        kwargs = {"packs": ["ts"], "personal": True, "packs_only": True}
    else:
        _update(root, agents, claude, home, packs=["ts"], personal=True)
        kwargs = {"packs": ["more"], "packs_only": True}
    before, calls = (_files(target), _files(root)), list(claude.calls)

    with pytest.raises(ValueError, match=message):
        _update(target, agents, claude, home, **kwargs)

    assert (_files(target), _files(root)) == before and claude.calls == calls


def test_a_personal_manifest_is_found_only_at_the_top_of_its_checkout(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts"], personal=True)
    (root / "web").mkdir()

    assert read_manifest(root)["profile"] == "personal" and read_manifest(root / "web") == {}
    assert manifest_version(root / "web") is None
    created = create_repository(
        root / "web" / "svc", name="svc", description="S.", python_version="3.12", git=False,
        lock=False, agents_dir=agents,
    )  # fmt: skip
    assert not created.errors and read_manifest(root / "web/svc")["profile"] == "python-uv"


def test_the_cli_adopts_personally_then_checks_clean(
    setup: tuple[Path, Path, FakeClaude, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    agents, root, _, _ = setup
    real = cli.update_repository
    monkeypatch.setattr(
        cli, "update_repository", lambda *args, **kwargs: real(*args, agents_dir=agents, **kwargs)
    )

    assert cli.main(["check", str(root), "--personal", "--pack", "ts"]) == 1
    planned = capsys.readouterr().out
    assert "+ .git/repo-template.json" in planned and ".mcp.json" not in planned
    assert cli.main(["update", str(root), "--personal", "--pack", "ts", "--no-input"]) == 0
    capsys.readouterr()
    assert cli.main(["check", str(root)]) == 0
    assert "Standards are current." in capsys.readouterr().out
    assert cli.main(["check", str(root), str(root)]) == 0
    assert capsys.readouterr().out.count("current (") == 2
    assert _status(root) == ""


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], Path]] = []

    def which(self, program: str) -> bool:
        return True

    def run(self, args: Sequence[str], cwd: Path) -> Completed:
        self.calls.append((list(args), cwd))
        return Completed(0)


def test_claude_cli_local_scope_runs_in_the_checkout_and_reads_its_entry(tmp_path: Path) -> None:
    home, project = tmp_path / "home", tmp_path / "repo"
    home.mkdir()
    (home / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {"global": {"url": "g"}},
                "projects": {str(project): {"mcpServers": {"docs": {"url": "d"}}}},
            }
        )
    )
    runner = Recorder()
    local = ClaudeCli(home, runner, project=project)
    elsewhere = ClaudeCli(home, runner, project=tmp_path / "other")

    local.add("docs", {"url": "d"})
    local.remove("docs")

    assert local.servers() == {"docs": {"url": "d"}} and elsewhere.servers() == {}
    assert ClaudeCli(home, runner).servers() == {"global": {"url": "g"}}
    assert runner.calls == [
        (["claude", "mcp", "add-json", "--scope", "local", "docs", '{"url":"d"}'], project),
        (["claude", "mcp", "remove", "--scope", "local", "docs"], project),
    ]


@pytest.mark.parametrize(
    "existing", ["", "mine\n", "mine", "a\n\nb\n", "# >>> other\nx\n# <<< other\n"]
)
def test_a_marked_block_is_removed_without_a_trace(existing: str) -> None:
    start, end = "# >>> s", "# <<< s"
    merged = merge_marked_block(existing, "x\ny", start, end)

    removed = remove_marked_block(merged, start, end)

    assert removed == (existing if existing.endswith("\n") or not existing else existing + "\n")
    assert remove_marked_block(existing, start, end) == existing


def test_the_report_uses_the_result_of_the_real_run(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    """The dry run that decides the exclude block reports nothing itself."""
    agents, root, claude, home = setup

    result = _update(root, agents, claude, home, packs=["ts"], personal=True)

    assert result.created.count(".claude/skills/ts-one") == 1 and not result.errors


def _commit(root: Path, files: Mapping[str, str], *also: str) -> None:
    """A teammate's commit of `files` (and paths `also`), and nothing else in the checkout."""
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    _git(root, "add", "--", *files, *also)
    _git(root, "commit", "-q", "-m", "team")


def test_links_and_codex_are_taken_out_when_the_team_un_ignores_them_later(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts"], personal=True)
    _commit(root, {".gitignore": "!.claude/skills/*\n!.agents/skills/*\n!.codex/config.toml\n"})
    assert _status(root) != ""  # the team's rule beats the exclude block

    planned = _update(root, agents, claude, home, check=True)
    applied = _update(root, agents, claude, home)
    again = _update(root, agents, claude, home, check=True)

    links = [".claude/skills/ts-one", ".agents/skills/ts-one"]
    assert planned.removed == applied.removed
    assert set(links) | {".codex/config.toml"} <= set(applied.removed)
    assert planned.preserved == applied.preserved == again.preserved
    assert len(again.preserved) == 2 and not again.removed and not again.created
    assert _status(root) == "" and not (root / ".codex").exists()


def test_a_team_skill_folder_that_replaces_a_link_shows_its_new_files(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts"], personal=True)
    (root / ".claude/skills/ts-one").unlink()  # a pull brings the team's own ts-one folder
    _commit(root, {".claude/skills/ts-one/SKILL.md": "team\n"})
    (root / ".claude/skills/ts-one/notes.md").write_text("new\n")

    assert "?? .claude/skills/ts-one/notes.md" in _status(root)  # before any update
    result = _update(root, agents, claude, home)

    assert any(".claude/skills/ts-one: the repository has its own" in n for n in result.notes)
    assert "/.claude/skills/ts-one\n" not in (root / ".git/info/exclude").read_text()


@pytest.mark.parametrize("flags", [{}, {"packs": ["more"]}, {"check": True}])
def test_a_linked_worktree_of_a_personal_checkout_is_refused(
    setup: tuple[Path, Path, FakeClaude, Path], tmp_path: Path, flags: dict[str, Any]
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts"], personal=True)
    linked = _worktree(root, tmp_path)
    before = _files(linked)

    with pytest.raises(ValueError, match="linked worktree of a checkout adopted personally"):
        _update(linked, agents, claude, home, **flags)

    assert _files(linked) == before and _status(linked) == ""


def test_your_own_visible_codex_config_is_never_written_or_hidden(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    (root / ".codex").mkdir()
    (root / ".codex/config.toml").write_text('model = "o3"\n')
    before = _status(root)

    planned = _update(root, agents, claude, home, check=True, packs=["ts"], personal=True)
    result = _update(root, agents, claude, home, packs=["ts"], personal=True)

    assert (root / ".codex/config.toml").read_text() == 'model = "o3"\n'
    assert _status(root) == before == "?? .codex/config.toml\n"
    note = (
        ".codex/config.toml holds settings of your own the repository doesn't ignore, so Codex "
        "gets no pack servers here"
    )
    assert note in planned.notes and note in result.notes
    assert not _update(root, agents, claude, home, check=True).needs_attention


def test_codex_config_the_team_ignores_gets_the_block(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _team_repo(tmp_path / "team", {".gitignore": ".codex/\n"})
    (root / ".codex").mkdir()
    (root / ".codex/config.toml").write_text('model = "o3"\n')
    home = tmp_path / "home"

    _update(root, agents, FakeClaude(home / ".claude.json"), home, packs=["ts"], personal=True)

    text = (root / ".codex/config.toml").read_text()
    assert text.startswith('model = "o3"\n') and "[mcp_servers.docs]" in text
    assert _status(root) == ""


def test_a_tracked_codex_config_gets_a_note_and_check_is_clean(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _team_repo(tmp_path / "team", {".codex/config.toml": 'model = "o3"\n'})
    home = tmp_path / "home"
    claude = FakeClaude(home / ".claude.json")

    result = _update(root, agents, claude, home, packs=["ts"], personal=True)

    assert "the repository tracks .codex/config.toml; no pack servers for Codex here" in (
        result.notes
    )
    assert (root / ".codex/config.toml").read_text() == 'model = "o3"\n' and _status(root) == ""
    assert not _update(root, agents, claude, home, check=True).needs_attention


def test_a_tracked_link_reached_through_a_linked_skills_folder_is_never_pruned(
    tmp_path: Path,
) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _team_repo(tmp_path / "team", {"tools/skills/README.md": "team\n"})
    (root / "tools/skills/ts-two").symlink_to(agents.absolute() / "packs/ts-two")  # looks ours
    (root / ".claude").mkdir()
    (root / ".claude/skills").symlink_to("../tools/skills")
    _commit(root, {}, "tools/skills/ts-two", ".claude/skills")
    home = tmp_path / "home"

    result = _update(
        root, agents, FakeClaude(home / ".claude.json"), home, packs=["ts"], personal=True
    )

    assert (root / "tools/skills/ts-two").is_symlink()
    assert not any("ts-two" in item for item in result.removed) and _status(root) == ""


def test_an_undefined_pack_keeps_its_local_server(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts"], personal=True)
    definitions = json.loads((agents / "skill-packs.json").read_text())
    (agents / "skill-packs.json").write_text(json.dumps({"more": definitions["more"]}))

    _update(root, agents, claude, home)
    _update(root, agents, claude, home)

    assert "docs" in claude.data and ("remove", "docs") not in claude.calls


def test_an_unreadable_state_file_is_an_error_not_a_crash(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    (home / ".repo-template").mkdir(parents=True)
    (home / ".repo-template/globals-state.json").write_text("{not json")

    result = _update(root, agents, claude, home, packs=["ts"], personal=True)

    assert any("delete it to reset" in error for error in result.errors)
    assert claude.calls == [] and _status(root) == ""


def test_an_unreadable_exclude_file_refuses_before_anything_is_written(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    (root / ".git/info").mkdir(exist_ok=True)
    (root / ".git/info/exclude").write_bytes(b"\xff\xfe not text\n")
    raw = (root / ".git/info/exclude").read_bytes()

    with pytest.raises(ValueError, match="cannot read"):
        _update(root, agents, claude, home, packs=["ts"], personal=True)

    assert (root / ".git/info/exclude").read_bytes() == raw
    assert not (root / ".git/repo-template.json").exists() and not (root / ".claude").exists()


def test_a_damaged_block_is_reported_and_left_alone(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    (root / ".git/info").mkdir(exist_ok=True)
    damaged = f"*.log\n{EXCLUDE_START}\n/.claude/skills/ts-one\nmine\n"
    (root / ".git/info/exclude").write_text(damaged)

    first = _update(root, agents, claude, home, packs=["ts"], personal=True)
    second = _update(root, agents, claude, home)

    assert (root / ".git/info/exclude").read_text() == damaged
    message = ".git/info/exclude (repo-template's block has lost a marker line; fix or delete it)"
    assert message in first.preserved and message in second.preserved


def test_an_exclude_file_linked_within_git_is_written_through(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    (root / ".git/excludes").write_text("*.log\n")
    (root / ".git/info").mkdir(exist_ok=True)
    (root / ".git/info/exclude").unlink(missing_ok=True)
    (root / ".git/info/exclude").symlink_to("../excludes")

    _update(root, agents, claude, home, packs=["ts"], personal=True)

    assert (root / ".git/info/exclude").is_symlink()
    assert EXCLUDE_START in (root / ".git/excludes").read_text() and _status(root) == ""


def test_an_exclude_file_linked_outside_the_checkout_is_left_alone(
    setup: tuple[Path, Path, FakeClaude, Path], tmp_path: Path
) -> None:
    agents, root, claude, home = setup
    shared = tmp_path / "shared-exclude"  # another checkout's, perhaps
    shared.write_text("*.log\n")
    (root / ".git/info").mkdir(exist_ok=True)
    (root / ".git/info/exclude").unlink(missing_ok=True)
    (root / ".git/info/exclude").symlink_to(shared)

    result = _update(root, agents, claude, home, packs=["ts"], personal=True)

    assert shared.read_text() == "*.log\n" and _status(root) == ""
    assert any(
        item.startswith(".git/info/exclude (a link to a file outside") for item in result.preserved
    )
    assert not (root / ".claude/skills/ts-one").exists()  # nothing would hide it


def test_the_real_local_scope_client_is_for_the_checkout(tmp_path: Path) -> None:
    client = real_local_claude(tmp_path / "repo", tmp_path / "home")

    assert isinstance(client, ClaudeCli)
    assert client.scope == "local" and client.project == tmp_path / "repo"


def test_claude_config_dir_elsewhere_skips_the_local_servers(
    setup: tuple[Path, Path, FakeClaude, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agents, root, claude, home = setup
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "other"))

    result = _update(root, agents, claude, home, packs=["ts"], personal=True)

    assert claude.calls == [] and any("CLAUDE_CONFIG_DIR is set" in n for n in result.notes)
    assert (root / ".claude/skills/ts-one").is_symlink()


def test_git_c_settings_still_reach_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A packs-only repository whose only ignore rule comes from `git -c core.excludesFile`."""
    agents = _catalog(tmp_path / "standards")
    root = _team_repo(tmp_path / "team")
    excludes = tmp_path / "excludes"
    excludes.write_text(".claude/\n.agents/\n.codex/\n")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.excludesFile")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(excludes))

    result = update_repository(root, packs=["more"], packs_only=True, agents_dir=agents)

    assert ".claude/skills/ts-two" in result.created and not result.preserved


def test_adopting_again_after_removing_servers_by_hand_adds_them_again(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts"], personal=True)
    claude.data.clear()  # `claude mcp remove docs --scope local`
    (root / ".git/repo-template.json").unlink()  # and the adoption undone by hand

    _update(root, agents, claude, home, packs=["ts"], personal=True)

    assert claude.calls == [("add", "docs"), ("add", "docs")] and "docs" in claude.data


def test_a_codex_folder_outside_the_repository_is_noted(tmp_path: Path) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _team_repo(tmp_path / "team")
    (tmp_path / "elsewhere").mkdir()
    (root / ".codex").symlink_to(tmp_path / "elsewhere")
    _git(root, "config", "core.excludesFile", str(tmp_path / "ignore"))
    (tmp_path / "ignore").write_text(".codex\n")
    home = tmp_path / "home"

    result = _update(
        root, agents, FakeClaude(home / ".claude.json"), home, packs=["ts"], personal=True
    )

    assert ".codex/config.toml resolves outside this repository; no pack servers for Codex" in (
        result.notes
    )
    assert not any((tmp_path / "elsewhere").iterdir()) and _status(root) == ""


@pytest.mark.parametrize(
    "rule", ["info/exclude", "excludesFile", "*.toml in info/exclude", "the same line as ours"]
)
def test_your_own_codex_config_hidden_by_your_own_rule_is_left_alone_every_run(
    setup: tuple[Path, Path, FakeClaude, Path], tmp_path: Path, rule: str
) -> None:
    agents, root, claude, home = setup
    (root / ".codex").mkdir()
    (root / ".codex/config.toml").write_text('model = "o3"\n')
    (root / ".git/info").mkdir(exist_ok=True)
    if rule == "excludesFile":
        (tmp_path / "mine").write_text(".codex/config.toml\n")
        _git(root, "config", "core.excludesFile", str(tmp_path / "mine"))
    else:
        line = {"info/exclude": ".codex/config.toml", "*.toml in info/exclude": "*.toml"}
        (root / ".git/info/exclude").write_text(line.get(rule, "/.codex/config.toml") + "\n")

    runs = [_update(root, agents, claude, home, packs=["ts"], personal=True) for _ in range(3)]

    assert (root / ".codex/config.toml").read_text() == 'model = "o3"\n'
    assert all(not r.updated and not r.removed for r in runs[1:]) and _status(root) == ""
    assert not _update(root, agents, claude, home, check=True).needs_attention


def test_settings_of_your_own_added_to_the_codex_file_take_the_block_out(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts", "more"], personal=True)
    definitions = json.loads((agents / "skill-packs.json").read_text())
    (agents / "skill-packs.json").write_text(json.dumps({"ts": definitions["ts"]}))  # undefined
    with (root / ".codex/config.toml").open("a") as handle:
        handle.write('model = "o3"\n')

    planned = _update(root, agents, claude, home, check=True)
    _update(root, agents, claude, home)

    assert ".codex/config.toml (pack MCP servers)" in planned.updated
    assert (root / ".codex/config.toml").read_text().strip() == 'model = "o3"'  # no machine paths
    assert _status(root) == "?? .codex/config.toml\n"  # yours now, shown like any file of yours


def test_a_link_at_a_folder_the_repository_tracks_but_hasnt_checked_out_goes(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts"], personal=True)
    blob = subprocess.run(
        [*GIT, "-C", str(root), "hash-object", "-w", "--stdin"],
        input="team\n", capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    name = ".claude/skills/ts-one/SKILL.md"  # committed, but not in this sparse checkout
    _git(root, "update-index", "--add", "--cacheinfo", f"100644,{blob},{name}")
    _git(root, "update-index", "--skip-worktree", name)
    _git(root, "commit", "-q", "-m", "team skill")

    planned = _update(root, agents, claude, home, check=True)
    applied = _update(root, agents, claude, home)

    assert ".claude/skills/ts-one" in planned.removed and planned.removed == applied.removed
    assert not (root / ".claude/skills/ts-one").is_symlink() and _status(root) == ""
    assert not _update(root, agents, claude, home, check=True).needs_attention


@pytest.mark.parametrize("check", [False, True])
def test_a_subfolder_of_a_personal_checkout_is_refused(
    setup: tuple[Path, Path, FakeClaude, Path], check: bool
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts"], personal=True)
    (root / "web").mkdir()

    with pytest.raises(ValueError, match="inside a checkout adopted personally"):
        _update(root / "web", agents, claude, home, check=check)

    assert not any((root / "web").iterdir()) and _status(root) == ""


def test_a_codex_folder_linked_within_the_repository_is_listed_where_it_resolves(
    tmp_path: Path,
) -> None:
    agents = _catalog(tmp_path / "standards")
    root = _team_repo(tmp_path / "team", {"config/codex/README.md": "codex\n"})
    (root / ".codex").symlink_to("config/codex")
    _commit(root, {}, ".codex")
    home = tmp_path / "home"
    claude = FakeClaude(home / ".claude.json")

    _update(root, agents, claude, home, packs=["ts"], personal=True)

    assert "[mcp_servers.docs]" in (root / "config/codex/config.toml").read_text()
    assert "/config/codex/config.toml\n" in (root / ".git/info/exclude").read_text()
    assert _status(root) == ""
    assert not _update(root, agents, claude, home, check=True).needs_attention


def test_links_to_an_old_target_or_of_an_undefined_pack_go_when_git_would_show_them(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts", "more"], personal=True)
    (agents / "skills/ts-one").mkdir(parents=True)  # where pack skills used to live
    old = root / ".claude/skills/ts-one"
    old.unlink()
    old.symlink_to(agents.absolute() / "skills/ts-one")
    definitions = json.loads((agents / "skill-packs.json").read_text())
    (agents / "skill-packs.json").write_text(json.dumps({"ts": definitions["ts"]}))
    _commit(root, {".gitignore": "!.claude/skills/*\n"})

    planned = _update(root, agents, claude, home, check=True)
    applied = _update(root, agents, claude, home)

    assert {".claude/skills/ts-one", ".claude/skills/ts-two"} <= set(applied.removed)
    assert planned.removed == applied.removed and _status(root) == ""


def test_a_codex_block_edited_by_hand_stays_hidden_when_it_cant_come_out(
    setup: tuple[Path, Path, FakeClaude, Path],
) -> None:
    agents, root, claude, home = setup
    _update(root, agents, claude, home, packs=["ts"], personal=True)
    path = root / ".codex/config.toml"
    edited = path.read_text().replace("startup_timeout_sec", "startup_timeout_sec_edited")
    path.write_text(edited.replace("https://docs.example.com/mcp", "https://mine.example.com"))
    with path.open("a") as handle:
        handle.write('model = "o3"\n')

    result = _update(root, agents, claude, home)

    assert any("edited inside the repo-template block" in item for item in result.preserved)
    assert "/.codex/config.toml" in (root / ".git/info/exclude").read_text()
    assert _status(root) == ""  # its machine paths stay hidden
