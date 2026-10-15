"""Exit codes are the CLI's contract with scripts and agents: 2 means "preserved for review"."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_template import __version__, cli
from repo_template.cli import main
from repo_template.scaffold import new_project


def _repository(root: Path) -> Path:
    new_project(root, name=root.name, description="Sample.", python_version="3.12")
    return root


def test_a_runtime_error_exits_1_with_a_message_not_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["check", str(tmp_path / "missing"), "--no-hooks", "--no-lock"])

    assert code == 1
    assert "repo-template: error: repository directory does not exist" in capsys.readouterr().err


def test_check_with_several_paths_prints_one_line_each(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current = _repository(tmp_path / "current")
    drifted = _repository(tmp_path / "drifted")
    (drifted / ".editorconfig").write_text("root = true\n")
    (drifted / "CHANGELOG.md").unlink()

    code = main(["check", str(current), str(drifted), "--no-hooks", "--no-lock"])

    lines = capsys.readouterr().out.splitlines()
    version = json.loads((current / ".repo-template.json").read_text())["template_version"]
    assert code == 1
    assert lines == [
        f"{current}: current ({version})",
        f"{drifted}: 1 to create, 1 to update, 1 for review ({version})",
    ]


def test_check_with_several_paths_is_0_when_all_are_current(tmp_path: Path) -> None:
    paths = [str(_repository(tmp_path / name)) for name in ("one", "two")]

    assert main(["check", *paths, "--no-hooks", "--no-lock"]) == 0


def test_globals_exits_1_when_it_reports_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    standards = tmp_path / "standards"
    (standards / ".agents/skills").mkdir(parents=True)
    (standards / ".agents/claude-settings.json").write_text('{"portable": {}, "defaults": {}}\n')
    overrides = {"gone": {"why": "test", "frontmatter": {"description": "x"}}}
    (standards / ".agents/skill-overrides.json").write_text(json.dumps(overrides))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    assert main(["globals", "--standards-root", str(standards)]) == 1


def test_check_with_several_paths_explains_each_failure_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current = _repository(tmp_path / "current")

    code = main(["check", str(current), str(tmp_path / "gone"), "--no-hooks", "--no-lock"])

    output = capsys.readouterr()
    assert code == 1
    assert f"{tmp_path / 'gone'}: error" in output.out
    assert "repo-template: error:" in output.err and "does not exist" in output.err


def test_update_reports_errors_before_preserved_files(tmp_path: Path) -> None:
    """With both, exit 1: fix what failed first, then decide the preserved files."""
    root = _repository(tmp_path / "service")
    (root / ".editorconfig").write_text("root = true\n")
    manifest_path = root / ".repo-template.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["skill_packs"] = ["not-a-defined-pack"]
    manifest_path.write_text(json.dumps(manifest))

    assert main(["update", str(root), "--no-hooks", "--no-lock", "--no-input"]) == 1


def test_an_interactive_update_keeps_first_pass_errors_in_its_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second pass sees pyproject.toml unchanged and doesn't retry `uv lock`, so a lock
    failure in the first pass must still fail the command."""
    from repo_template import cli
    from repo_template.repository import Completed, update_repository

    root = _repository(tmp_path / "service")
    (root / ".editorconfig").write_text("root = true\n")  # a conflict to resolve
    (root / "uv.lock").write_text("version = 1\n")  # so only the first pass tries to re-lock
    pyproject = root / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('"ruff>=', '"ruff-not>='))

    class FailingLock:
        def which(self, program: str) -> bool:
            return program == "uv"

        def run(self, args: object, cwd: Path) -> Completed:
            return Completed(1, err="network down")

    def with_failing_lock(*args: object, **kwargs: object) -> object:
        return update_repository(*args, **kwargs, runner=FailingLock())  # type: ignore[arg-type]

    class Keep:
        def say(self, text: str = "") -> None: ...
        def diff(self, lines: object) -> None: ...
        def choose(self, question: str, options: object) -> str:
            return "k"

    monkeypatch.setattr(cli, "update_repository", with_failing_lock)
    monkeypatch.setattr(cli, "_interactive", lambda args: True)
    monkeypatch.setattr(cli, "TerminalPrompt", Keep)

    assert main(["update", str(root), "--no-hooks"]) == 1


def test_globals_exits_2_when_it_preserves_a_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    standards = tmp_path / "standards"
    skill = standards / ".agents/skills/example"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: example\ndescription: x\n---\n")
    (standards / ".claude/skills/example").mkdir(parents=True)  # a real folder, not a link
    (standards / ".agents/claude-settings.json").write_text('{"portable": {}, "defaults": {}}\n')
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    assert main(["globals", "--standards-root", str(standards)]) == 2


def test_version_names_the_release_and_the_checkout_it_runs_from(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["--version"])

    assert stopped.value.code == 0
    root = Path(__file__).resolve().parents[1]
    assert capsys.readouterr().out == f"repo-template {__version__} ({root})\n"


def test_version_keeps_a_long_checkout_path_on_one_line(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path("/Users/someone/Library/CloudStorage/OneDrive-Company-Name/Projects/repo-template")
    monkeypatch.setattr(cli, "installed_root", lambda: root)
    monkeypatch.setenv("COLUMNS", "40")

    with pytest.raises(SystemExit):
        main(["--version"])

    assert capsys.readouterr().out == f"repo-template {__version__} ({root})\n"
