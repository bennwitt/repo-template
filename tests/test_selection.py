"""Catalog browsing and selection preserve ownership across all adoption profiles."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from repo_template import catalog_view, cli
from repo_template.repository import create_repository, update_repository
from repo_template.scaffold import read_manifest
from repo_template.selection import Selection


@pytest.fixture
def catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    agents = home / ".agents"
    for directory, name in (("skills", "core"), ("packs", "one"), ("packs", "two")):
        folder = agents / directory / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Work with {name}.\n---\n"
        )
    (agents / "skill-packs.json").write_text(
        json.dumps(
            {
                "tools": {"description": "Two tools", "skills": ["one", "two"], "mcp": ["docs"]},
                "shared": {"description": "Shared tool", "skills": ["two"]},
            }
        )
    )
    (agents / "mcp-servers.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "servers": {
                    "docs": {
                        "scope": "pack",
                        "url": "https://docs.example.com/mcp",
                        "source": "s",
                        "why": "w",
                    }
                },
            }
        )
    )
    (agents / "claude-settings.json").write_text('{"portable": {}, "defaults": {}}\n')
    monkeypatch.setattr(cli, "AGENTS_DIR", agents)
    monkeypatch.setattr(
        cli,
        "update_repository",
        lambda *a, **kw: update_repository(*a, **kw, agents_dir=agents, home=home),
    )
    return agents


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True)


def repo(root: Path) -> Path:
    root.mkdir()
    git(root, "init", "-q")
    (root / ".gitignore").write_text(".agents/\n.claude/\n.codex/\n")
    (root / "README.md").write_text("Keep the project's documentation.\n")
    return root


def snapshot(root: Path) -> dict[str, bytes | str]:
    return {
        str(p.relative_to(root)): str(p.readlink()) if p.is_symlink() else p.read_bytes()
        for p in root.rglob("*")
        if p.is_symlink() or p.is_file()
    }


@pytest.mark.parametrize("profile", ["full", "packs-only", "personal"])
def test_select_remove_overlap_and_idempotence(catalog: Path, tmp_path: Path, profile: str) -> None:
    root = repo(tmp_path / "project")
    if profile == "personal":
        (root / ".gitignore").unlink()
    before_status = git(root, "status", "--porcelain")
    options = dict(agents_dir=catalog, home=tmp_path / "home", hooks=False, lock=False)
    adoption = {"packs_only": profile == "packs-only", "personal": profile == "personal"}
    before = snapshot(root)
    preview = update_repository(root, check=True, skills=["one"], **adoption, **options)
    assert snapshot(root) == before
    result = update_repository(root, skills=["one"], **adoption, **options)
    assert not result.errors and not result.preserved
    assert preview.created == result.created
    assert read_manifest(root)["individual_skills"] == ["one"]
    assert not (root / ".mcp.json").exists()  # individual selection brings no pack server
    for client in (".agents", ".claude"):
        assert (root / client / "skills/one").resolve() == catalog / "packs/one"
    assert not update_repository(root, check=True, **options).needs_attention
    update_repository(root, packs=["tools", "shared"], **options)
    # Removing a pack keeps individually selected one and two from the remaining pack.
    update_repository(root, remove_packs=["tools"], **options)
    assert (root / ".agents/skills/one").exists()
    assert (root / ".agents/skills/two").exists()
    if (root / ".mcp.json").exists():
        assert not json.loads((root / ".mcp.json").read_text()).get("mcpServers")
    own = root / ".agents/skills/own"
    own.mkdir()
    (own / "SKILL.md").write_text("Project's skill.")
    update_repository(root, remove_packs=["shared"], remove_skills=["one"], **options)
    assert not (root / ".agents/skills/one").is_symlink()
    assert not (root / ".agents/skills/two").is_symlink()
    assert (own / "SKILL.md").read_text() == "Project's skill."
    assert not update_repository(root, check=True, **options).needs_attention
    if profile == "personal":
        own.joinpath("SKILL.md").unlink()
        own.rmdir()
        assert git(root, "status", "--porcelain") == before_status
        assert not (root / "AGENTS.md").exists()
    if profile != "full":
        assert (root / "README.md").read_text() == "Keep the project's documentation.\n"
        assert not (root / "docs/agents/workflow.md").exists()


def test_removing_individual_keeps_pack_skill_and_server(catalog: Path, tmp_path: Path) -> None:
    root = repo(tmp_path / "project")
    options = dict(agents_dir=catalog, hooks=False, lock=False)
    update_repository(root, packs=["tools"], skills=["one"], packs_only=True, **options)
    update_repository(root, remove_skills=["one"], **options)
    assert (root / ".agents/skills/one").exists()
    assert "docs" in json.loads((root / ".mcp.json").read_text())["mcpServers"]
    assert "individual_skills" not in read_manifest(root)


@pytest.mark.parametrize("name", ["absent", "../one", "/tmp/one", "core"])
def test_bad_skill_refused_before_any_write(catalog: Path, tmp_path: Path, name: str) -> None:
    root = repo(tmp_path / "project")
    before = snapshot(root)
    with pytest.raises(ValueError):
        update_repository(root, packs=["tools"], skills=[name], agents_dir=catalog)
    assert snapshot(root) == before


def test_missing_recorded_skill_keeps_links_until_explicitly_removed(
    catalog: Path, tmp_path: Path
) -> None:
    root = repo(tmp_path / "project")
    options = dict(agents_dir=catalog, hooks=False, lock=False)
    update_repository(root, skills=["one"], packs_only=True, **options)
    (catalog / "packs/one/SKILL.md").unlink()
    result = update_repository(root, **options)
    assert result.errors
    assert (root / ".agents/skills/one").is_symlink()
    update_repository(root, remove_skills=["one"], **options)
    assert not (root / ".agents/skills/one").is_symlink()


def test_new_repository_accepts_individual_skills(catalog: Path, tmp_path: Path) -> None:
    root = tmp_path / "new"
    result = create_repository(
        root,
        name="new",
        description="x",
        python_version="3.12",
        git=False,
        lock=False,
        skills=["one"],
        agents_dir=catalog,
    )
    assert not result.errors
    assert read_manifest(root)["individual_skills"] == ["one"]
    assert (root / ".agents/skills/one").exists()


def test_catalog_json_marks_explicit_and_pack_supplied(
    catalog: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo(tmp_path / "project")
    update_repository(root, packs_only=True, packs=["tools"], skills=["one"], agents_dir=catalog)
    before = snapshot(tmp_path)
    assert (
        cli.main(
            [
                "globals",
                "--standards-root",
                str(catalog.parent),
                "--list",
                "--json",
                "--repo",
                str(root),
            ]
        )
        == 0
    )
    listing = json.loads(capsys.readouterr().out)
    by_name = {e["kind"] + ":" + e["name"]: e for e in listing["entries"]}
    assert by_name["pack:tools"]["selected"]
    assert by_name["pack:tools"]["mcp"] == ["docs"]
    assert by_name["skill:one"]["selected"]
    assert by_name["skill:two"]["supplied_by"] == ["tools"]
    assert not by_name["skill:two"]["selected"]
    assert by_name["skill:core"]["global_skill"]
    assert snapshot(tmp_path) == before


def test_cli_scripted_preview_and_apply(catalog: Path, tmp_path: Path) -> None:
    root = repo(tmp_path / "project")
    before = snapshot(root)
    args = [str(root), "--packs-only", "--skill", "one"]
    assert cli.main(["check", *args]) == 1
    assert snapshot(root) == before
    assert cli.main(["update", *args, "--no-input"]) == 0
    assert cli.main(["check", str(root)]) == 0
    assert cli.main(["update", str(root), "--remove-skill", "one", "--no-input"]) == 0
    assert not (root / ".agents/skills/one").is_symlink()


@pytest.mark.parametrize("answers", [["q"], ["skill:one", "done", "n"], []])
def test_picker_cancel_and_eof_write_nothing(
    catalog: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answers: list[str]
) -> None:
    root = repo(tmp_path / "project")
    before = snapshot(root)
    replies = iter(answers)

    def answer(prompt: str) -> str:
        try:
            return next(replies)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr(cli, "_interactive", lambda args: True)
    monkeypatch.setattr("builtins.input", answer)
    assert cli.main(["update", str(root), "--select", "--packs-only"]) == 0
    assert snapshot(root) == before


def test_picker_filters_toggles_and_confirms_preview(
    catalog: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = repo(tmp_path / "project")
    replies = iter(["/one", "nonsense", "skill:one", "done", "y"])

    def answer(prompt: str) -> str:
        if prompt.startswith("Apply"):
            assert not (root / ".repo-template.json").exists()
            assert "Would create" in capsys.readouterr().out
        return next(replies)

    monkeypatch.setattr(cli, "_interactive", lambda args: True)
    monkeypatch.setattr("builtins.input", answer)
    assert cli.main(["update", str(root), "--select", "--packs-only"]) == 0
    assert read_manifest(root)["individual_skills"] == ["one"]


def test_picker_nonterminal_refused(catalog: Path, tmp_path: Path) -> None:
    root = repo(tmp_path / "project")
    before = snapshot(root)
    assert cli.main(["update", str(root), "--select", "--no-input"]) == 1
    assert snapshot(root) == before


def test_picker_starts_with_existing_and_can_deselect_missing(
    catalog: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies = iter(["pack:gone skill:one", "done"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
    assert catalog_view.choose(catalog, Selection(("gone",), ("one",))) == Selection()


@pytest.mark.parametrize(
    "field,value",
    [("individual_skills", ["../escape"]), ("individual_skills", "one"), ("skill_packs", [None])],
)
def test_malformed_selection_refused_before_writes(
    catalog: Path, tmp_path: Path, field: str, value: object
) -> None:
    root = repo(tmp_path / "project")
    update_repository(root, skills=["one"], packs_only=True, agents_dir=catalog)
    manifest = read_manifest(root)
    manifest[field] = value
    (root / ".repo-template.json").write_text(json.dumps(manifest))
    before = snapshot(root)
    with pytest.raises(ValueError):
        update_repository(root, agents_dir=catalog)
    assert snapshot(root) == before


def test_selection_does_not_replace_foreign_skill(catalog: Path, tmp_path: Path) -> None:
    root = repo(tmp_path / "project")
    own = root / ".agents/skills/one"
    own.mkdir(parents=True)
    (own / "SKILL.md").write_text("Project-owned")
    result = update_repository(root, skills=["one"], packs_only=True, agents_dir=catalog)
    assert result.preserved
    assert (own / "SKILL.md").read_text() == "Project-owned"
    update_repository(root, remove_skills=["one"], agents_dir=catalog)
    assert (own / "SKILL.md").read_text() == "Project-owned"


def test_contradictory_add_remove_refused_before_writes(catalog: Path, tmp_path: Path) -> None:
    root = repo(tmp_path / "project")
    before = snapshot(root)
    with pytest.raises(ValueError, match="cannot add and remove"):
        update_repository(root, skills=["one"], remove_skills=["one"], agents_dir=catalog)
    assert snapshot(root) == before


def test_older_cli_refuses_individual_manifest(
    catalog: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from repo_template import scaffold

    root = repo(tmp_path / "project")
    update_repository(root, skills=["one"], packs_only=True, agents_dir=catalog)
    before = snapshot(root)
    monkeypatch.setattr(scaffold, "__version__", "0.5.4")
    with pytest.raises(ValueError, match="newer than this"):
        update_repository(root, agents_dir=catalog)
    assert snapshot(root) == before


@pytest.mark.parametrize("mode", ["packs", "skills"])
def test_catalog_text_filters_and_shows_descriptions(
    catalog: Path, capsys: pytest.CaptureFixture[str], mode: str
) -> None:
    assert cli.main(["globals", "--standards-root", str(catalog.parent), "--list", mode]) == 0
    text = capsys.readouterr().out
    assert "Two tools" in text if mode == "packs" else "Work with one." in text
    assert "skill:core" not in text if mode == "packs" else "global; installed by globals" in text


@pytest.mark.parametrize("answer", ["n", "y"])
def test_picker_in_real_terminal(catalog: Path, tmp_path: Path, answer: str) -> None:
    import errno
    import os
    import pty
    import select
    import sys
    import time

    root = repo(tmp_path / "project")
    (root / ".gitignore").unlink()  # personal adoption must provide its own ignores
    before = snapshot(root)
    master, slave = pty.openpty()
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(tmp_path / "unused-client-config"))
    process = subprocess.Popen(
        [sys.executable, "-m", "repo_template.cli", "update", str(root), "--personal", "--select"],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
    )
    os.close(slave)
    transcript = b""
    pending = b""
    exchanges = iter(
        [
            (b"Selection> ", b"skill:one\n"),
            (b"Selection> ", b"done\n"),
            (b"[y/N] ", answer.encode() + b"\n"),
        ]
    )
    expected = next(exchanges, None)
    deadline = time.monotonic() + 20
    try:
        while time.monotonic() < deadline:
            if not select.select([master], [], [], 0.1)[0]:
                if process.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master, 65536)
            except OSError as exc:
                if exc.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            transcript += chunk
            pending += chunk
            if expected and expected[0] in pending:
                if expected[0] == b"[y/N] ":
                    assert snapshot(root) == before
                    assert b"Would create" in transcript
                os.write(master, expected[1])
                pending = b""
                expected = next(exchanges, None)
        assert process.wait(timeout=2) == 0, transcript.decode(errors="replace")
        assert expected is None, transcript.decode(errors="replace")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
    if answer == "n":
        assert snapshot(root) == before
    else:
        assert read_manifest(root)["individual_skills"] == ["one"]
        assert git(root, "status", "--porcelain") == "?? README.md\n"
        assert (root / ".agents/skills/one").resolve() == catalog / "packs/one"


def test_dual_manifest_recovery_clears_both_selections(catalog: Path, tmp_path: Path) -> None:
    root = repo(tmp_path / "project")
    update_repository(
        root, skills=["one"], personal=True, agents_dir=catalog, home=tmp_path / "home"
    )
    (root / ".repo-template.json").write_text('{"profile": "packs-only"}')
    with pytest.raises(ValueError, match="skill_packs and individual_skills"):
        update_repository(root, agents_dir=catalog)


def test_catalog_terminal_text_escapes_controls_but_json_retains_data(
    catalog: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    description = "Clear\x1b[2J\x1b[H\rforged\nrow\u202e"
    (catalog / "packs/one/SKILL.md").write_text(
        "---\nname: one\ndescription: " + json.dumps(description) + "\n---\n"
    )
    catalog_view.show_catalog(catalog, "skills", Selection(), json_output=False)
    printed = capsys.readouterr().out
    assert "\x1b" not in printed and "\r" not in printed and "\u202e" not in printed
    assert "\\x1b" in printed
    answers = iter(["skills", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert catalog_view.choose(catalog, Selection()) is None
    printed = capsys.readouterr().out
    assert "\x1b" not in printed and "\r" not in printed and "\u202e" not in printed
    catalog_view.show_catalog(catalog, "skills", Selection(), json_output=True)
    listing = json.loads(capsys.readouterr().out)
    assert next(e for e in listing["entries"] if e["name"] == "one")["description"] == description
