# Repository guide

This repository owns the standard used to create and update other repositories.

## Purpose

`repo-template` is the single maintained source for repository engineering defaults and portable
AI-development configuration across machines. Domain terms are defined in `GLOSSARY.md`.

## Boundaries

The CLI creates and updates Python/uv repository scaffolding (or, with `--packs-only`, only a
repository's skill packs and their MCP servers; with `--personal`, those for one person, in
a repository whose tracked and visible files it never changes) and installs global symlinks. It
does not create GitHub repositories, commit or push, copy secrets, or overwrite conflicting
project-owned files. The one generated file that writes to GitHub is the baseline's pre-push
hook: after a push, a read-only `claude -p` fills in the pull request's description, which
`gh pr edit` saves. `globals` also installs the global MCP servers, through
`claude mcp add-json --scope user` and into `~/.codex/config.toml`, and `update` writes a
repository's pack MCP servers (`.mcp.json`, and an ignored `.codex/config.toml`; for a personal
repository Claude Code's local scope instead of `.mcp.json`, plus `.git/repo-template.json` and a
block in `.git/info/exclude`). Only
`globals --upstream` (read-only: GitHub, npm and PyPI) and `globals --upgrade` (skills, and MCP
server re-pins) use the network; `--upgrade` records the files it vendors (skills and license
copies) with `git add -N` and leaves committing to you.

`setup-machine.sh` (macOS and Linux) sets up a machine in one run: it clones or pulls the standards
repository (only a clean `main`), installs the CLI with `uv tool install --editable`, previews
`globals` before applying it, and offers the optional tools at the versions
`.agents/machine-tools.json` pins (`azd` only once its download's SHA-256 matches). Every
install it offers asks first, with optional tools defaulting to no. In a shell profile it writes
only its marked block, after a backup in `~/.repo-template/backups/`. `--check` reports what is
set up and changes nothing.

## Commands

For skill selection, review scope and repository workflow setup, read
[docs/agents/workflow.md](docs/agents/workflow.md).

- Install: `uv sync --dev`
- Test: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .` (CI and the pre-commit hook run `ruff format --check .`)
- Type-check: `uv run mypy src`
- Self-check: `uv run repo-template check .` prints "Standards are current."
- Catalog listing, read-only: `uv run repo-template globals --list --standards-root .`
- Catalog validation, read-only: `uv run repo-template globals --check --standards-root .`

## Design rules

- Keep the public CLI small: `new`, `update`, `check`, and `globals`.
- Updates must be idempotent and must not overwrite unrecognized user changes.
- A clean `check` means `update` has nothing to do.
- Keep project-specific instructions in generated `AGENTS.md`; keep reusable workflows in global skills.
- Never copy Claude credentials, history, caches, or machine state into this repository.
- Add tests for any change to rendering, update conflict handling, symlink behavior, personal
  adoption, `setup-machine.sh` (`tests/test_setup_machine.py`: stand-ins for `uv`,
  `repo-template` and the tools it installs, a temporary HOME, and `_converse` for answers typed
  in a terminal), or the pre-push hook (`tests/test_pr_description.py`: stand-ins for `gh` and
  `claude` that keep a pull request's state in files).
- Try commands against temporary folders: `check` and `update` on a repository made in
  `mktemp -d`, and `HOME=$(mktemp -d) uv run repo-template globals --check --standards-root .`.
  A plain `globals` or a real `setup-machine.sh` run changes this machine: run one only when the
  user asks.
- A change users can see goes into `CHANGELOG.md` (Unreleased) and into every document that
  shows it: `README.md`, `HOW_TO_UPDATE_MACHINE_AND_ITS_REPOS.md`, the `repo-template` skill, and
  `GLOSSARY.md` for a new term.
- Every skill is recorded and licensed: vendored ones in the lock (and byte-identical to it,
  except the frontmatter fields an override changes), local ones in
  `.agents/skill-sources.json`. Run `repo-template globals --standards-root .` after catalog
  changes; it records overrides and, once the catalog is clean, regenerates the README catalog
  and notices.

## Safety invariants

- Existing unrecognized content is preserved.
- Replaced global files are backed up before symlinks are installed.
- `~/.claude` itself is never symlinked; individual skills are, and the portable settings are
  merged into `~/.claude/settings.json` without overwriting entries changed on the machine.
- Generated repositories never commit `.agents`, `.claude`, `.codex`, `.env`, or private keys.
- Hooks in the portable settings always exit 0, so they can never block a session.
- The generated pre-push hook always exits 0 and works in the background, so it can never block
  a push, and it writes only over a description nobody wrote: empty, the untouched template,
  the commit messages alone, or its own unedited one.
- MCP servers are keyless and read-only, defined once in `.agents/mcp-servers.json`, and each
  denied tool is denied in both clients. repo-template never writes approval settings
  (`enableAllProjectMcpServers`, `enabledMcpjsonServers`) or Codex `[projects]`, trust,
  sandbox or approval settings, and an MCP entry changed by hand is kept.
