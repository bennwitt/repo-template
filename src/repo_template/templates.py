from __future__ import annotations

from textwrap import dedent

from repo_template.model import ProjectContext, TemplateFile
from repo_template.policies import PolicyName


def _clean(value: str) -> str:
    return dedent(value).lstrip("\n").rstrip() + "\n"


def _render(value: str, context: ProjectContext) -> str:
    for token, replacement in context.substitutions().items():
        value = value.replace(token, replacement)
    return _clean(value)


def project_files(context: ProjectContext) -> list[TemplateFile]:
    """Return the complete, rendered Python/uv baseline."""
    files: list[TemplateFile] = []

    def add(
        path: str,
        content: str,
        *,
        policy: PolicyName = "managed",
        executable: bool = False,
        legacy_path: str | None = None,
    ) -> None:
        files.append(TemplateFile(path, _render(content, context), policy, executable, legacy_path))

    add(
        "pyproject.toml",
        """
        [project]
        name = "__PROJECT_NAME__"
        version = "0.1.0"
        description = __TOML_DESCRIPTION__
        readme = "README.md"
        requires-python = ">=__PYTHON_VERSION__"
        dependencies = []

        [build-system]
        requires = ["uv_build>=0.12.17,<0.13.0"]
        build-backend = "uv_build"

        [dependency-groups]
        dev = [
            "mypy>=1.18",
            "pytest>=8.4",
            "pytest-cov>=7.0",
            "ruff>=0.13",
        ]

        [tool.pytest.ini_options]
        addopts = "-q --strict-markers"
        testpaths = ["tests"]

        [tool.ruff]
        line-length = 100
        target-version = "__PYTHON_TARGET__"

        [tool.ruff.lint]
        select = ["E", "F", "I", "B", "UP", "SIM"]

        [tool.mypy]
        python_version = "__PYTHON_VERSION__"
        strict = true
        packages = ["__PACKAGE_NAME__"]
        """,
        policy="toml_merge",
    )
    add(
        "README.md",
        """
        # __PROJECT_NAME__

        __DESCRIPTION__

        ## Development

        ```bash
        uv sync --dev
        uv run pytest
        uv run ruff check .
        uv run mypy src
        ```

        Copy `.env.example` to `.env` for local configuration. Never commit `.env`.
        """,
        policy="seed",
    )
    add(
        "CHANGELOG.md",
        """
        # Changelog

        All notable changes to this project are recorded here.

        ## Unreleased

        - Initial project structure.
        """,
        policy="seed",
    )
    add(
        "GLOSSARY.md",
        """
        # __PROJECT_NAME__

        __DESCRIPTION__

        ## Language

        <!-- Add a term once its meaning is settled. Terms only: no implementation details.

        **Term**:
        One or two sentences on what it is.
        _Avoid_: other words for the same thing
        -->
        """,
        policy="seed",
        legacy_path="CONTEXT.md",
    )
    add(
        "AGENTS.md",
        """
        # Repository guide

        ## Purpose

        __DESCRIPTION__

        ## Boundaries

        Record what this system owns, what it integrates with, and what is out of scope.

        ## Commands

        - Install: `uv sync --dev`
        - Test: `uv run pytest`
        - Lint: `uv run ruff check .`
        - Format: `uv run ruff format .`
        - Type-check: `uv run mypy src`

        ## Layout

        - Application code: `src/__PACKAGE_NAME__/`
        - Tests: `tests/`
        - Domain terms: `GLOSSARY.md`
        - Architecture decisions: `docs/adr/`

        ## Working agreements

        - Keep changes scoped and add tests for behavior changes.
        - Use `uv` for dependencies and commands; commit `uv.lock`.
        - Add a term to `GLOSSARY.md` once its meaning is settled; keep it to terms only.
        - Update the Purpose and Boundaries sections above when the system's scope changes.
        - Add an ADR when a durable architectural decision needs explanation.
        - Never commit secrets, `.env`, personal agent state, or credentials.
        """,
        policy="seed",
    )
    add("CLAUDE.md", "@AGENTS.md")
    add(".python-version", "__PYTHON_VERSION__")
    add(
        ".editorconfig",
        """
        root = true

        [*]
        charset = utf-8
        end_of_line = lf
        insert_final_newline = true
        trim_trailing_whitespace = true
        indent_style = space
        indent_size = 4

        [*.{yml,yaml,json}]
        indent_size = 2

        [*.md]
        trim_trailing_whitespace = false
        """,
    )
    add(
        ".gitattributes",
        """
        * text=auto eol=lf
        *.sh text eol=lf
        *.bat text eol=crlf
        """,
    )
    add(
        ".gitignore",
        """
        # Python
        __pycache__/
        *.py[cod]
        *.egg-info/
        .venv/
        dist/
        build/

        # Test and tool caches
        .coverage
        htmlcov/
        .pytest_cache/
        .mypy_cache/
        .ruff_cache/

        # Local configuration and secrets
        .env
        .env.*
        !.env.example
        *.pem
        *.key

        # Personal AI tooling is centralized outside each repository
        .agents/
        .claude/
        .codex/
        CLAUDE.local.md

        # Editors and operating systems
        .idea/
        .DS_Store
        """,
        policy="gitignore",
    )
    add(
        ".env.example",
        """
        # Copy to .env and fill in local values. Never commit .env.
        APP_ENV=development
        LOG_LEVEL=INFO
        """,
        policy="seed",
    )
    add(
        ".vscode/extensions.json",
        """
        {
          "recommendations": [
            "ms-python.python",
            "charliermarsh.ruff",
            "openai.chatgpt",
            "anthropic.claude-code"
          ]
        }
        """,
        policy="json_merge",
    )
    add(
        ".vscode/settings.json",
        """
        {
          "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
          "python.testing.pytestEnabled": true,
          "python.testing.unittestEnabled": false,
          "python.testing.pytestArgs": ["tests"],
          "editor.formatOnSave": true,
          "[python]": {
            "editor.defaultFormatter": "charliermarsh.ruff",
            "editor.codeActionsOnSave": {
              "source.fixAll.ruff": "explicit",
              "source.organizeImports.ruff": "explicit"
            }
          }
        }
        """,
        policy="json_merge",
    )
    add(
        ".vscode/tasks.json",
        """
        {
          "version": "2.0.0",
          "tasks": [
            {
              "label": "Sync dependencies",
              "type": "shell",
              "command": "uv sync --dev",
              "problemMatcher": []
            },
            {
              "label": "Test",
              "type": "shell",
              "command": "uv run pytest",
              "group": {"kind": "test", "isDefault": true},
              "problemMatcher": []
            },
            {
              "label": "Lint",
              "type": "shell",
              "command": "uv run ruff check .",
              "group": "build",
              "problemMatcher": []
            },
            {
              "label": "Type check",
              "type": "shell",
              "command": "uv run mypy src",
              "group": "build",
              "problemMatcher": []
            }
          ]
        }
        """,
        policy="json_merge",
    )
    add(
        ".github/workflows/ci.yml",
        """
        name: CI

        on:
          push:
            branches: [main]
          pull_request:

        permissions:
          contents: read

        concurrency:
          group: ${{ github.workflow }}-${{ github.ref }}
          cancel-in-progress: true

        jobs:
          quality:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
                with:
                  persist-credentials: false
              - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
                with:
                  enable-cache: true
              - run: uv python install
              - run: uv sync --locked --dev
              - run: uv run ruff check .
              - run: uv run ruff format --check .
              - run: uv run mypy src
              - run: uv run pytest
        """,
    )
    add(
        ".github/dependabot.yml",
        """
        version: 2
        updates:
          - package-ecosystem: uv
            directory: /
            schedule:
              interval: weekly
          - package-ecosystem: github-actions
            directory: /
            schedule:
              interval: weekly
        """,
    )
    add(
        ".github/PULL_REQUEST_TEMPLATE.md",
        """
        ## Description

        <!-- What changed and why. Link the issue or spec it addresses, e.g. "Closes #123". -->

        ## Type of change

        - [ ] 🐞 Bug fix
        - [ ] ✨ Feature
        - [ ] ⚡ Enhancement
        - [ ] 🧹 Refactor
        - [ ] 🧪 Tests
        - [ ] 📜 Documentation
        - [ ] 🚀 Infrastructure / CI
        - [ ] 💥 Breaking change <!-- explain the migration under Risk and rollback -->

        ## Areas affected

        - [ ] ⚙️ Application / API (`src/`)
        - [ ] 🎨 Frontend / UI
        - [ ] 💾 Data / migrations
        - [ ] 📦 Dependencies (`pyproject.toml`, `uv.lock`)
        - [ ] 🛠️ Tooling, scripts or Git hooks
        - [ ] 🏗️ CI, GitHub or infrastructure
        - [ ] 📜 Documentation (`README.md`, `AGENTS.md`, `GLOSSARY.md`, `docs/adr/`)

        ## How to verify

        <!-- Steps a reviewer can follow, one action and its expected outcome per line. -->

        - [ ] **Action:** <!-- e.g. `uv run app load a.csv` --> → **Outcome:** <!-- 3 rows saved -->
        - [ ] **Action:** <!-- e.g. rerun the import --> → **Outcome:** <!-- no duplicates -->

        ## Checks

        - [ ] `uv run ruff check .` and `uv run ruff format --check .`
        - [ ] `uv run mypy src`
        - [ ] `uv run pytest`, with tests added or updated for changed behavior
        - [ ] `AGENTS.md`, `GLOSSARY.md` or an ADR updated when scope, terms or decisions changed

        ## Risk and rollback

        <!-- What could break, who is affected, and how to undo it, including migrations. -->
        """,
    )
    add(
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        """
        name: Bug report
        description: Report reproducible incorrect behavior
        title: "[Bug]: "
        labels: [bug]
        body:
          - type: textarea
            id: behavior
            attributes:
              label: What happened?
              description: Include expected and actual behavior.
            validations:
              required: true
          - type: textarea
            id: reproduce
            attributes:
              label: Reproduction steps
            validations:
              required: true
          - type: textarea
            id: environment
            attributes:
              label: Environment
              description: OS, Python version, and relevant dependency versions.
        """,
        policy="seed",
    )
    add(
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        """
        name: Feature request
        description: Propose an improvement
        title: "[Feature]: "
        labels: [enhancement]
        body:
          - type: textarea
            id: problem
            attributes:
              label: Problem
              description: What user or system need is not being met?
            validations:
              required: true
          - type: textarea
            id: outcome
            attributes:
              label: Desired outcome
            validations:
              required: true
          - type: textarea
            id: alternatives
            attributes:
              label: Alternatives considered
        """,
        policy="seed",
    )
    add(
        ".githooks/pre-commit",
        r"""
        #!/usr/bin/env sh
        set -eu

        secret_pattern='BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|AKIA[0-9A-Z]{16}'
        secret_pattern="${secret_pattern}|sk-proj-[A-Za-z0-9_-]{40,}|sk-[A-Za-z0-9]{32,}"
        if git diff --cached --binary | grep -Eq "$secret_pattern"; then
          echo "Possible secret in staged changes; commit stopped." >&2
          exit 1
        fi

        uv lock --check
        uv run ruff check .
        uv run ruff format --check .
        uv run mypy src
        uv run pytest
        """,
        executable=True,
    )
    add(
        ".ai/receipt-policy.json",
        """
        {
          "mode": "announce",
          "logPath": ".ai/skill-receipts.jsonl"
        }
        """,
    )
    add(".ai/.gitignore", "skill-receipts.jsonl")
    add(
        "docs/adr/README.md",
        """
        # Architecture decision records

        Add numbered records such as `0001-use-postgresql.md` with:

        - Context
        - Decision
        - Consequences
        - Status
        """,
        policy="seed",
    )
    add(
        f"src/{context.package_name}/__init__.py",
        '"""__PROJECT_NAME__ package."""\n\n__version__ = "0.1.0"',
        policy="seed",
    )
    add(f"src/{context.package_name}/py.typed", "")
    add(
        "tests/test_smoke.py",
        """
        import __PACKAGE_NAME__


        def test_package_imports() -> None:
            assert __PACKAGE_NAME__.__version__ == "0.1.0"
        """,
        policy="seed",
    )
    return files
