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


MYPY_TABLE = """
[tool.mypy]
python_version = "__PYTHON_VERSION__"
strict = true
packages = ["__PACKAGE_NAME__"]
"""


BUILD_SYSTEM = """
[build-system]
requires = ["uv_build>=0.12.17,<0.13.0"]
build-backend = "uv_build"

"""  # src/<package>/ is installed into the environment, so its tests can import it


def project_files(context: ProjectContext, *, package: bool = True) -> list[TemplateFile]:
    """Return the complete, rendered Python/uv baseline.

    `package` is False for an existing repository whose code isn't in `src/<package>/`: the
    package scaffold, its smoke test and the mypy table that names the package are left out.
    """
    files: list[TemplateFile] = []

    def add(
        path: str,
        content: str,
        *,
        policy: PolicyName = "managed",
        executable: bool = False,
        legacy_path: str | None = None,
        legacy_hint: str = "",
    ) -> None:
        rendered = _render(content, context)
        files.append(TemplateFile(path, rendered, policy, executable, legacy_path, legacy_hint))

    add(
        "pyproject.toml",
        dedent(
            """
        [project]
        name = "__PROJECT_NAME__"
        version = "0.1.0"
        description = __TOML_DESCRIPTION__
        readme = "README.md"
        requires-python = ">=__PYTHON_VERSION__"
        dependencies = []
        __BUILD_SYSTEM__
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
        """
        ).replace("__BUILD_SYSTEM__\n", BUILD_SYSTEM if package else "")
        + (MYPY_TABLE if package else ""),
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
        legacy_hint=(
            "git mv CONTEXT.md GLOSSARY.md, then move sections that aren't terms into AGENTS.md"
        ),
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

        - Application code: __CODE_PATH__
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
        """.replace("__CODE_PATH__", "`src/__PACKAGE_NAME__/`" if package else "`src/`"),
        policy="seed",
        legacy_path="CLAUDE.md",
        legacy_hint="move its guide into AGENTS.md, then make CLAUDE.md just @AGENTS.md",
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

        # Tool state: browser sessions, saved logins and test reports, cloud environment
        # settings, Foundry datasets
        .playwright-cli/
        .playwright-mcp/
        .auth/
        test-results/
        playwright-report/
        blob-report/
        .azure/
        .foundry/

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

        secret_pattern='BEGIN ([A-Z0-9]+ )*PRIVATE KEY|(AKIA|ASIA)[0-9A-Z]{16}'
        secret_pattern="${secret_pattern}|sk-(proj|svcacct|admin|ant)-[A-Za-z0-9_-]{40,}"
        secret_pattern="${secret_pattern}|sk-[A-Za-z0-9]{32,}|hf_[A-Za-z0-9]{30,}"
        secret_pattern="${secret_pattern}|LLM[|][0-9]{6,}[|][A-Za-z0-9_-]{16,}"
        # Only the lines being added (removing a key doesn't stop the commit), marked '>' so a
        # line starting with '++' isn't taken for a file header, whatever the user's diff
        # settings (colour, external diff tools, textconv), and in any encoding (LC_ALL=C -a).
        added=$(git diff --cached --binary -U0 --no-color --no-ext-diff --no-textconv \
          --output-indicator-new='>' | LC_ALL=C grep -a '^>' || true)
        if printf '%s\n' "$added" | LC_ALL=C grep -aEq "$secret_pattern"; then
          echo "Possible secret in staged changes; commit stopped." >&2
          exit 1
        fi

        # Git points hooks at this commit's index (and, in a worktree, its repository); tests
        # that run git in a temporary folder would write there, so the checks run without them
        unset $(git rev-parse --local-env-vars)
        uv lock --check
        uv run ruff check .
        uv run ruff format --check .
        uv run mypy src
        uv run pytest
        """,
        executable=True,
    )
    add(
        ".githooks/pre-push",
        r"""
        #!/usr/bin/env sh
        # After each push of a branch, fills in its pull request's description from the diff, in
        # the background: a push never waits for it or fails because of it. It writes only over a
        # description that is empty, the untouched PR template, nothing but the branch's commit
        # messages (what `gh pr create --fill` writes), or its own that nobody has edited since;
        # any other is someone's and stays. Needs `claude` and `gh`, signed in. PR_DESCRIPTION=0
        # turns it off; it waits up to PR_DESCRIPTION_WAIT seconds (default 600) for the pull
        # request to be opened. What it did: .git/pr-description.log
        set -u

        if [ "${1:-}" != --fill ]; then
          # Git runs this as `pre-push <remote> <url>`, one line per pushed ref on standard input
          refs=$(cat)
          [ "${PR_DESCRIPTION:-1}" != 0 ] || exit 0
          command -v claude >/dev/null 2>&1 && command -v gh >/dev/null 2>&1 || exit 0
          common=$(git rev-parse --git-common-dir 2>/dev/null) || exit 0
          default=$(git symbolic-ref --quiet --short "refs/remotes/${1:-origin}/HEAD" 2>/dev/null)
          default=${default#"${1:-origin}"/}
          hook="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
          log="$common/pr-description.log"
          printf '%s\n' "$refs" | while read -r _ oid ref _; do
            case $ref in refs/heads/*) ;; *) continue ;; esac  # a branch, not a tag
            case $oid in *[!0]*) ;; *) continue ;; esac  # pushed, not deleted
            branch=${ref#refs/heads/}
            case $branch in main | master | "$default") continue ;; esac
            echo "Filling in $branch's pull request description in the background ($log)" >&2
            nohup sh "$hook" --fill "$branch" "$oid" </dev/null >>"$log" 2>&1 &
          done
          exit 0
        fi

        branch=$2
        oid=$3
        say() { echo "$(date '+%Y-%m-%d %H:%M:%S') $branch $(printf %.7s "$oid"): $*"; }
        # Line endings, trailing spaces and blank lines at either end don't count as an edit
        normalized() { sed -e 's/[[:space:]]*$//' -e '/./,$!d'; }
        marker='<!-- Written by .githooks/pre-push; rewritten on each push until edited. hash:'
        work=$(mktemp -d) || exit 0
        trap 'rm -rf "$work"' EXIT

        # The pull request this push updates: wait until one is open and shows this commit
        waited=0
        while :; do
          if found=$(gh pr view "$branch" --json number,state,headRefOid \
            --jq '"\(.number) \(.state) \(.headRefOid)"' 2>"$work/err"); then
            number=${found%% *}
            [ "${found#* }" = "OPEN $oid" ] && break
          elif ! grep -qi 'no pull requests found' "$work/err"; then
            say "gh couldn't look up the pull request: $(cat "$work/err")"
            exit 0
          fi
          if [ "$waited" -ge "${PR_DESCRIPTION_WAIT:-600}" ]; then
            say "no open pull request shows this commit after ${waited}s; nothing to fill in"
            exit 0
          fi
          sleep 15
          waited=$((waited + 15))
        done

        # Whose description it is
        gh pr view "$number" --json body --jq .body >"$work/body" 2>"$work/err" || {
          say "gh couldn't read #$number: $(cat "$work/err")"
          exit 0
        }
        body=$(normalized <"$work/body")
        template=
        for path in .github/PULL_REQUEST_TEMPLATE.md .github/pull_request_template.md \
          PULL_REQUEST_TEMPLATE.md pull_request_template.md \
          docs/PULL_REQUEST_TEMPLATE.md docs/pull_request_template.md; do
          template=$(git show "$oid:$path" 2>/dev/null | normalized)
          [ -z "$template" ] || break
        done
        first=$(printf '%s\n' "$body" | sed -n 1p)
        rest=$(printf '%s\n' "$body" | sed 1d | normalized)
        why=
        if [ -z "$body" ]; then
          why="it was empty"
        elif [ -n "$template" ] && [ "$body" = "$template" ]; then
          why="it was the untouched template"
        elif [ "$first" = "$marker$(printf '%s\n' "$rest" | git hash-object --stdin) -->" ]; then
          why="it was this hook's, unedited"
        else
          gh pr view "$number" --json commits --jq '.commits[] | .messageHeadline, .messageBody' \
            2>/dev/null | normalized >"$work/messages"
          if [ -s "$work/messages" ] && ! printf '%s\n' "$body" | sed 's/^[-*] //' |
            grep -v '^$' | grep -Fxvq -f "$work/messages"; then
            why="it held only the commit messages"
          fi
        fi
        if [ -z "$why" ]; then
          say "#$number's description was written by someone; left alone"
          exit 0
        fi

        # Write it: claude reads the pull request and the repository, and can change nothing
        if [ -n "$template" ]; then
          shape="Fill in this pull request template. Keep its headings and checklists, tick only
        the boxes the change shows to be true, replace each <!-- --> comment with what it asks
        for, and leave a box unticked when you can't tell (a check you didn't see pass, a step
        only a person can do).

        $template"
        else
          shape="Use three sections: Summary, How to verify, and Risk and rollback."
        fi
        cat >"$work/prompt" <<EOF
        Write the description of pull request #$number in this repository, as of commit $oid.
        Read the change with \`gh pr diff $number\`, its title and commits with
        \`gh pr view $number --json title,baseRefName,commits\`, and its checks with
        \`gh pr checks $number\`; open any file you need. AGENTS.md and GLOSSARY.md, if present,
        give the repository's purpose and terms. Keep it short and concrete, and reply with the
        description alone, in Markdown: no preamble and no code fence around it.

        $shape
        EOF
        if ! claude -p --output-format text --tools Read,Grep,Glob,Bash \
          --allowedTools Read Grep Glob "Bash(gh pr view:*)" "Bash(gh pr diff:*)" \
          "Bash(gh pr checks:*)" --permission-mode dontAsk --strict-mcp-config \
          --setting-sources project --no-session-persistence \
          <"$work/prompt" >"$work/new" 2>"$work/err"; then
          say "claude couldn't write it: $(tail -n 3 "$work/err")"
          exit 0
        fi
        new=$(normalized <"$work/new")
        if [ -z "$new" ]; then
          say "claude wrote nothing; #$number left alone"
          exit 0
        fi

        # Unless a later push, a merge or an edit came first
        latest=$(gh pr view "$number" --json state,headRefOid \
          --jq '"\(.state) \(.headRefOid)"' 2>/dev/null)
        gh pr view "$number" --json body --jq .body >"$work/now" 2>/dev/null
        if [ "$latest" != "OPEN $oid" ] || [ "$(normalized <"$work/now")" != "$body" ]; then
          say "#$number changed while its description was written; left alone"
          exit 0
        fi
        hash=$(printf '%s\n' "$new" | git hash-object --stdin)
        printf '%s%s -->\n\n%s\n' "$marker" "$hash" "$new" >"$work/out"
        if gh pr edit "$number" --body-file "$work/out" >/dev/null 2>"$work/err"; then
          say "filled in #$number's description ($why)"
        else
          say "gh couldn't save #$number's description: $(cat "$work/err")"
        fi
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
    if package:
        add(
            f"src/{context.package_name}/__init__.py",
            '"""__PROJECT_NAME__ package."""\n\n__version__ = "0.1.0"',
            policy="seed",
        )
        add(f"src/{context.package_name}/py.typed", "")
        add(
            "tests/test_smoke.py",
            """
            from importlib.metadata import version

            import __PACKAGE_NAME__


            def test_version_matches_package_metadata() -> None:
                assert __PACKAGE_NAME__.__version__ == version("__PROJECT_NAME__")
            """,
            policy="seed",
        )
    return files
