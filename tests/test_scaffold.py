from __future__ import annotations

import json
import os
import subprocess
import tomllib
from pathlib import Path

import pytest

from repo_template import scaffold
from repo_template.policies import GITIGNORE_END, GITIGNORE_START
from repo_template.scaffold import (
    new_project,
    normalize_project_name,
    package_name,
    update_project,
)


def test_normalizes_repository_and_package_names() -> None:
    assert normalize_project_name("My Useful API") == "my-useful-api"
    assert package_name("my-useful-api") == "my_useful_api"
    assert package_name("123-api") == "project_123_api"
    with pytest.raises(ValueError):
        normalize_project_name("---")


def test_new_project_is_complete_and_immediately_current(tmp_path: Path) -> None:
    root = tmp_path / "sample-project"
    result = new_project(
        root,
        name="sample-project",
        description='Handles "sample" work.',
        python_version="3.12",
    )

    assert not result.errors
    assert (root / "src/sample_project/__init__.py").is_file()
    assert (root / ".githooks/pre-commit").stat().st_mode & 0o111
    assert GITIGNORE_START in (root / ".gitignore").read_text()
    assert GITIGNORE_END in (root / ".gitignore").read_text()
    assert (
        tomllib.loads((root / "pyproject.toml").read_text())["project"]["description"]
        == 'Handles "sample" work.'
    )
    manifest = json.loads((root / ".repo-template.json").read_text())
    assert manifest["project"]["package"] == "sample_project"

    current = update_project(root, check=True)
    assert not current.needs_attention


def test_update_adds_missing_and_preserves_modified_managed_file(tmp_path: Path) -> None:
    root = tmp_path / "sample"
    new_project(root, name="sample", description="Sample.", python_version="3.12")
    (root / ".editorconfig").unlink()
    workflow = root / ".github/workflows/ci.yml"
    workflow.write_text("name: Custom CI\n")

    result = update_project(root)

    assert ".editorconfig" in result.created
    assert ".github/workflows/ci.yml" in result.preserved
    assert workflow.read_text() == "name: Custom CI\n"


def test_update_adopts_existing_pyproject_without_replacing_metadata(tmp_path: Path) -> None:
    root = tmp_path / "existing"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        """
[project]
name = "existing-app"
version = "9.1.0"
description = "Keep me"
requires-python = ">=3.11"
dependencies = ["httpx>=0.28"]
""".lstrip()
    )

    result = update_project(root)
    parsed = tomllib.loads((root / "pyproject.toml").read_text())

    assert "pyproject.toml" in result.updated
    assert parsed["project"]["version"] == "9.1.0"
    assert parsed["project"]["dependencies"] == ["httpx>=0.28"]
    assert {item.split(">=")[0] for item in parsed["dependency-groups"]["dev"]} == {
        "mypy",
        "pytest",
        "pytest-cov",
        "ruff",
    }
    assert "ruff" in parsed["tool"]
    assert "mypy" in parsed["tool"]
    assert "pytest" in parsed["tool"]


def test_json_update_adds_recommendations_without_removing_existing(tmp_path: Path) -> None:
    root = tmp_path / "existing"
    root.mkdir()
    vscode = root / ".vscode/extensions.json"
    vscode.parent.mkdir()
    vscode.write_text('{"recommendations": ["custom.extension"]}\n')

    update_project(root)
    recommendations = json.loads(vscode.read_text())["recommendations"]

    assert recommendations[0] == "custom.extension"
    assert "openai.chatgpt" in recommendations
    assert "anthropic.claude-code" in recommendations


def test_new_refuses_nonempty_target(tmp_path: Path) -> None:
    root = tmp_path / "occupied"
    root.mkdir()
    (root / "important.txt").write_text("keep")

    with pytest.raises(ValueError, match="not empty"):
        new_project(root, name="occupied", description="Occupied.", python_version="3.12")


def test_new_project_uses_a_glossary_and_keeps_scope_in_agents_md(tmp_path: Path) -> None:
    root = tmp_path / "sample"
    new_project(root, name="sample", description="Handles samples.", python_version="3.12")

    assert (root / "GLOSSARY.md").read_text().startswith("# sample\n\nHandles samples.\n")
    assert not (root / "CONTEXT.md").exists()
    agents = (root / "AGENTS.md").read_text()
    assert "## Purpose\n\nHandles samples." in agents
    assert "## Boundaries" in agents


def test_update_asks_for_a_manual_rename_of_context_md(tmp_path: Path) -> None:
    root = tmp_path / "older"
    new_project(root, name="older", description="Older.", python_version="3.12")
    (root / "GLOSSARY.md").rename(root / "CONTEXT.md")

    result = update_project(root)

    assert not (root / "GLOSSARY.md").exists()
    assert [item for item in result.preserved if item.startswith("CONTEXT.md")] == [
        "CONTEXT.md (now GLOSSARY.md: git mv CONTEXT.md GLOSSARY.md, then move sections "
        "that aren't terms into AGENTS.md)"
    ]

    (root / "CONTEXT.md").rename(root / "GLOSSARY.md")
    assert not update_project(root, check=True).needs_attention


def test_project_owned_files_are_left_alone_and_stay_owned(tmp_path: Path) -> None:
    root = tmp_path / "custom"
    new_project(root, name="custom", description="Custom.", python_version="3.12")
    workflow = root / ".github/workflows/ci.yml"
    workflow.write_text("name: Custom CI\n")
    assert ".github/workflows/ci.yml" in update_project(root, check=True).preserved

    manifest_path = root / ".repo-template.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["project_owned"] = [".github/workflows/ci.yml"]
    manifest_path.write_text(json.dumps(manifest))

    planned = update_project(root, check=True)
    assert planned.preserved == []
    assert planned.updated == [".repo-template.json"]  # its stale hash for ci.yml is dropped
    update_project(root)
    assert not update_project(root, check=True).needs_attention
    assert workflow.read_text() == "name: Custom CI\n"
    assert json.loads(manifest_path.read_text())["project_owned"] == [".github/workflows/ci.yml"]


def _existing_repository(root: Path, *, claude: str | None = None) -> Path:
    (root / "src/chat").mkdir(parents=True)
    (root / "src/chat/__init__.py").write_text("")
    (root / "src/config.py").write_text("")
    (root / "pyproject.toml").write_text('[project]\nname = "flat-app"\nversion = "1.0.0"\n')
    if claude is not None:
        (root / "CLAUDE.md").write_text(claude)
    return root


def test_adoption_keeps_a_flat_src_layout(tmp_path: Path) -> None:
    root = _existing_repository(tmp_path / "checkout-dir")

    update_project(root)

    assert not (root / "src/flat_app").exists()
    assert not (root / "tests/test_smoke.py").exists()
    assert "mypy" not in tomllib.loads((root / "pyproject.toml").read_text())["tool"]
    assert "- Application code: `src/`" in (root / "AGENTS.md").read_text()
    manifest = json.loads((root / ".repo-template.json").read_text())
    assert manifest["project"]["description"] == "flat-app project."
    assert not update_project(root, check=True).needs_attention


def test_adoption_asks_to_move_an_existing_claude_guide_into_agents_md(tmp_path: Path) -> None:
    root = _existing_repository(tmp_path / "guided", claude="# Guide\n\nRun the tests.\n")

    result = update_project(root)

    assert not (root / "AGENTS.md").exists()
    assert [item for item in result.preserved if item.startswith("CLAUDE.md")] == [
        "CLAUDE.md (now AGENTS.md: move its guide into AGENTS.md, then make CLAUDE.md just "
        "@AGENTS.md)"
    ]

    (root / "AGENTS.md").write_text("# Guide\n\nRun the tests.\n")
    (root / "CLAUDE.md").write_text("@AGENTS.md\n")
    assert update_project(root, check=True).updated == [".repo-template.json"]
    update_project(root)
    assert not update_project(root, check=True).needs_attention


def test_a_bare_claude_import_does_not_block_agents_md(tmp_path: Path) -> None:
    root = _existing_repository(tmp_path / "bare", claude="@AGENTS.md\n")

    update_project(root)

    assert (root / "AGENTS.md").is_file()


def test_check_reports_the_manifest_rewrite_a_new_version_needs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clean check means update has nothing to do, including the manifest's own version."""
    root = tmp_path / "service"
    new_project(root, name="service", description="Service.", python_version="3.12")
    monkeypatch.setattr(scaffold, "__version__", "99.0.0")

    planned = update_project(root, check=True)

    assert planned.updated == [".repo-template.json"]
    assert json.loads((root / ".repo-template.json").read_text())["template_version"] != "99.0.0"
    update_project(root)
    assert json.loads((root / ".repo-template.json").read_text())["template_version"] == "99.0.0"
    assert not update_project(root, check=True).needs_attention


def test_an_older_cli_refuses_a_manifest_from_a_newer_one(tmp_path: Path) -> None:
    """Otherwise a machine that hasn't pulled would downgrade every managed file."""
    root = tmp_path / "service"
    new_project(root, name="service", description="Service.", python_version="3.12")
    manifest_path = root / ".repo-template.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["template_version"] = "99.0.0"
    manifest_path.write_text(json.dumps(manifest))
    before = manifest_path.read_text()

    with pytest.raises(ValueError, match="git pull"):
        update_project(root)
    with pytest.raises(ValueError, match="newer than this"):
        update_project(root, check=True)
    assert manifest_path.read_text() == before


def test_a_deleted_project_owned_file_stays_deleted(tmp_path: Path) -> None:
    root = tmp_path / "renovate"
    new_project(root, name="renovate", description="Uses Renovate.", python_version="3.12")
    manifest_path = root / ".repo-template.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["project_owned"] = [".github/dependabot.yml"]
    manifest_path.write_text(json.dumps(manifest))
    (root / ".github/dependabot.yml").unlink()

    update_project(root)

    assert not (root / ".github/dependabot.yml").exists()
    assert not update_project(root, check=True).needs_attention


def test_a_complete_json_file_keeps_its_own_formatting(tmp_path: Path) -> None:
    root = tmp_path / "service"
    new_project(root, name="service", description="Service.", python_version="3.12")
    settings = root / ".vscode/settings.json"
    four_spaces = json.dumps(json.loads(settings.read_text()), indent=4) + "\n"
    settings.write_text(four_spaces)

    result = update_project(root)

    assert ".vscode/settings.json" in result.unchanged
    assert settings.read_text() == four_spaces


@pytest.mark.parametrize(
    ("owned", "legacy", "content"),
    [("AGENTS.md", "CLAUDE.md", "# Our guide\n"), ("GLOSSARY.md", "CONTEXT.md", "# Terms\n")],
)
def test_a_deleted_owned_file_is_not_offered_a_move_from_its_old_name(
    tmp_path: Path, owned: str, legacy: str, content: str
) -> None:
    """Owning AGENTS.md (or GLOSSARY.md) and deleting it is a decision about CLAUDE.md
    (or CONTEXT.md) too: update must not ask to move it on every run."""
    root = tmp_path / "service"
    new_project(root, name="service", description="Service.", python_version="3.12")
    manifest_path = root / ".repo-template.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["project_owned"] = [owned]
    manifest_path.write_text(json.dumps(manifest))
    (root / owned).unlink()
    (root / legacy).write_text(content)

    result = update_project(root)

    assert not (root / owned).exists()
    assert not [item for item in result.preserved if item.startswith(legacy + " (now")]
    assert not result.conflicts or all(conflict.moves_to is None for conflict in result.conflicts)


def test_versions_compare_as_major_minor_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "service"
    new_project(root, name="service", description="Service.", python_version="3.12")
    manifest_path = root / ".repo-template.json"
    manifest = json.loads(manifest_path.read_text())
    monkeypatch.setattr(scaffold, "__version__", "0.4")
    manifest["template_version"] = "0.4.0"
    manifest_path.write_text(json.dumps(manifest))

    update_project(root, check=True)  # "0.4" and "0.4.0" are one release: no refusal

    manifest["template_version"] = "0.4.1"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="newer than this"):
        update_project(root, check=True)


HF = "hf_" + "a1B2" * 9  # tokens are built at run time, so this file never holds one
SCAN_CASES = [
    ("token = '" + HF + "'", True, []),
    ("key = 'LLM|" + "1234567890" + "|" + "AbCd_ef-" * 4 + "'", True, []),
    ("key = 'sk-proj-" + "x" * 48 + "'", True, []),
    ("key = 'sk-ant-" + "x" * 48 + "'", True, []),
    ("id = 'ASIA" + "ABCDEFGHIJKLMNOP" + "'", True, []),
    ("-----BEGIN ENCRYPTED " + "PRIVATE KEY-----", True, []),
    ("token = '" + HF + "'", True, ["-c", "color.ui=always", "-c", "color.diff=always"]),
    ("token = '" + HF + "'", True, ["-c", "diff.external=true"]),
    ("++ " + HF, True, []),  # shown as '+++ ...', like a file header
    ("caf\xe9 = '" + HF + "'", True, []),  # Latin-1, not UTF-8
    ("hf_short = 1", False, []),
    ("model = 'facebook/sam3'", False, []),
]


def _git_repo(tmp_path: Path) -> tuple[Path, list[str]]:
    import shutil

    if shutil.which("git") is None:
        pytest.skip("needs git")
    root = tmp_path / "repo"
    new_project(root, name="repo", description="R.", python_version="3.12")
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@e"]
    subprocess.run([*git, "init", "-q"], check=True)
    return root, git


@pytest.mark.parametrize(("line", "stopped", "settings"), SCAN_CASES)
def test_the_pre_commit_hook_stops_added_secrets(
    tmp_path: Path, line: str, stopped: bool, settings: list[str]
) -> None:
    root, git = _git_repo(tmp_path)
    hook = root / ".githooks/pre-commit"
    scan = hook.read_text().split("\nuv lock --check")[0] + "\n"  # the scan, not the checks
    (root / "scan.sh").write_text(scan)
    for value in settings[1::2]:
        name, _, setting = value.partition("=")
        subprocess.run([*git, "config", name, setting], check=True)
    (root / "config.py").write_bytes(line.encode("latin-1") + b"\n")
    subprocess.run([*git, "add", "config.py"], check=True)

    added = subprocess.run(["sh", str(root / "scan.sh")], cwd=root, capture_output=True)

    assert (added.returncode == 1) is stopped, added.stderr
    if stopped:  # removing the same line later doesn't stop that commit
        subprocess.run([*git, "commit", "-qm", "x", "-n"], check=True)
        (root / "config.py").write_text("")
        subprocess.run([*git, "add", "config.py"], check=True)
        removed = subprocess.run(["sh", str(root / "scan.sh")], cwd=root, capture_output=True)
        assert removed.returncode == 0, removed.stderr


def test_the_pre_commit_checks_run_without_this_commits_git_context(tmp_path: Path) -> None:
    """A commit from a worktree hands hooks GIT_DIR and GIT_INDEX_FILE. A test the hook runs
    that calls `git -C <tmp> init` must not write to the repository being committed (that set
    core.bare and a user in this repository's config once)."""
    root, git = _git_repo(tmp_path)
    subprocess.run([*git, "config", "core.hooksPath", ".githooks"], check=True)
    (root / ".gitignore").write_text("worktree/\n")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "start", "-n"], check=True)
    work = root / "worktree"
    subprocess.run([*git, "worktree", "add", "-q", "-b", "side", str(work)], check=True)
    stub = tmp_path / "bin"
    stub.mkdir()
    probe = tmp_path / "probe"
    (stub / "uv").write_text(  # stands in for the checks: a test that runs git in a temp dir
        f"#!/bin/sh\ngit -C {probe} init -q && git -C {probe} config user.name x\nexit 0\n"
    )
    (stub / "uv").chmod(0o755)
    probe.mkdir()
    before = (root / ".git/config").read_text()
    (work / "new.txt").write_text("x\n")
    env = {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}"}
    subprocess.run(["git", "-C", str(work), "add", "new.txt"], check=True, env=env)

    done = subprocess.run(
        ["git", "-C", str(work), "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "y"],
        capture_output=True, text=True, env=env,
    )  # fmt: skip

    assert done.returncode == 0, done.stderr
    assert (root / ".git/config").read_text() == before
    assert (probe / ".git").is_dir()  # the stand-in ran, in its own folder


def test_the_global_excludes_ignore_playwright_state() -> None:
    from repo_template.standards import GITIGNORE_CONTENT

    assert "**/.playwright-cli/" in GITIGNORE_CONTENT
    assert "**/.playwright-mcp/" in GITIGNORE_CONTENT
