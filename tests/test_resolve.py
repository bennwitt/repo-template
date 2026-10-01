from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from repo_template.repository import SUBPROCESS
from repo_template.resolve import Options, resolve_conflicts
from repo_template.scaffold import new_project, update_project


class ScriptedPrompt:
    """Answers questions from a script and records everything said."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.said: list[str] = []

    def say(self, text: str = "") -> None:
        self.said.append(text)

    def diff(self, lines: Sequence[str]) -> None:
        self.said.extend(lines)

    def choose(self, question: str, options: Options) -> str:
        answer = self.answers.pop(0)
        assert answer in {key for key, _ in options}, (answer, options)
        return answer


def _repository(root: Path) -> Path:
    new_project(root, name=root.name, description="Sample.", python_version="3.12")
    return root


def _edit_editorconfig(root: Path) -> str:
    baseline = (root / ".editorconfig").read_text()
    edited = (
        baseline.replace("indent_size = 4", "indent_size = 2")
        + "\n[Makefile]\nindent_style = tab\n"
    )
    (root / ".editorconfig").write_text(edited)
    return baseline


def _resolve(root: Path, *answers: str) -> tuple[list[tuple[str, str]], ScriptedPrompt]:
    conflicts = update_project(root).conflicts
    prompt = ScriptedPrompt(*answers)
    return resolve_conflicts(root, conflicts, prompt, SUBPROCESS), prompt


def test_use_the_baseline_overwrites_the_file(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    baseline = _edit_editorconfig(root)

    outcomes, prompt = _resolve(root, "o")

    assert outcomes == [(".editorconfig", "used the baseline")]
    assert any(line.startswith("+indent_size = 4") for line in prompt.said)
    assert (root / ".editorconfig").read_text() == baseline
    assert not update_project(root, check=True).needs_attention


def test_keep_yours_is_asked_again_only_when_the_baseline_changes(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    _edit_editorconfig(root)
    edited = (root / ".editorconfig").read_text()

    _resolve(root, "k")

    assert (root / ".editorconfig").read_text() == edited
    assert not update_project(root, check=True).needs_attention
    update_project(root)  # rewriting the manifest keeps the acceptance
    assert not update_project(root, check=True).needs_attention

    manifest_path = root / ".repo-template.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][".editorconfig"]["accepted"]["baseline"] = "an older baseline"
    manifest_path.write_text(json.dumps(manifest))
    assert ".editorconfig" in update_project(root, check=True).preserved


def test_merge_takes_each_change_as_chosen(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    baseline = _edit_editorconfig(root)

    # Change 1: indent_size 2 vs 4 -> keep yours. Change 2: the [Makefile] section -> remove it.
    outcomes, _ = _resolve(root, "m", "n", "y")

    merged = (root / ".editorconfig").read_text()
    assert outcomes == [(".editorconfig", "merged")]
    assert merged == baseline.replace("indent_size = 4", "indent_size = 2")
    assert not update_project(root, check=True).needs_attention


def test_merge_that_ends_up_equal_to_the_baseline_counts_as_using_it(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    baseline = _edit_editorconfig(root)

    outcomes, _ = _resolve(root, "m", "y", "y")

    assert outcomes == [(".editorconfig", "used the baseline")]
    assert (root / ".editorconfig").read_text() == baseline


def test_always_keep_makes_the_file_project_owned(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    _edit_editorconfig(root)

    _resolve(root, "a")

    manifest = json.loads((root / ".repo-template.json").read_text())
    assert manifest["project_owned"] == [".editorconfig"]
    assert not update_project(root, check=True).needs_attention


def test_skip_leaves_the_file_for_later(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    _edit_editorconfig(root)

    outcomes, _ = _resolve(root, "s")

    assert outcomes == [(".editorconfig", "skipped")]
    assert ".editorconfig" in update_project(root, check=True).preserved


def test_unparseable_json_can_be_kept(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    settings = root / ".vscode/settings.json"
    settings.write_text("{\n  // team default\n" + settings.read_text()[2:])

    outcomes, prompt = _resolve(root, "k")

    assert outcomes == [(".vscode/settings.json", "kept yours")]
    assert "[1/1] .vscode/settings.json (invalid JSON)" in prompt.said
    assert not update_project(root, check=True).needs_attention


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True
    ).stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_move_claude_guide_into_agents_md_keeps_history(tmp_path: Path) -> None:
    root = tmp_path / "guided"
    (root / "src/app").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "guided"\nversion = "1.0.0"\n')
    (root / "CLAUDE.md").write_text("# Guide\n\nRun the tests. See CLAUDE.md.\n")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "start")

    outcomes, prompt = _resolve(root, "m")

    assert outcomes == [("CLAUDE.md", "moved (staged with git mv)")]
    assert any("commit the staged moves on their own" in line for line in prompt.said)
    assert (root / "AGENTS.md").read_text() == "# Guide\n\nRun the tests. See CLAUDE.md.\n"
    assert (root / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    assert "R  CLAUDE.md -> AGENTS.md" in _git(root, "status", "--short")
    assert any("AGENTS.md:3:Run the tests. See CLAUDE.md." in line for line in prompt.said)


def test_move_context_md_without_git(tmp_path: Path) -> None:
    root = _repository(tmp_path / "older")
    (root / "GLOSSARY.md").rename(root / "CONTEXT.md")

    outcomes, _ = _resolve(root, "m")

    assert outcomes == [("CONTEXT.md", "moved")]
    assert (root / "GLOSSARY.md").is_file()
    assert not (root / "CONTEXT.md").exists()
    assert not update_project(root, check=True).needs_attention
