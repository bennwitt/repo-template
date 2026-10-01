from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

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
