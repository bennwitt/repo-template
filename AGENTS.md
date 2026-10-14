# Repository guide

This repository owns the standard used to create and update other repositories.

## Purpose

`repo-template` is the single maintained source for repository engineering defaults and portable
AI-development configuration across machines. Domain terms are defined in `GLOSSARY.md`.

## Boundaries

The CLI creates and updates Python/uv repository scaffolding and installs global symlinks. It does
not create GitHub repositories, commit or push, copy secrets, or overwrite conflicting
project-owned files. `globals` also installs the global MCP servers, through
`claude mcp add-json --scope user` and into `~/.codex/config.toml`, and `update` writes a
repository's pack MCP servers (`.mcp.json`, and an ignored `.codex/config.toml`). Only
`globals --upstream` (read-only) and `globals --upgrade` use the network;
`--upgrade` records the files it vendors (skills and license copies) with `git add -N` and
leaves committing to you.

## Commands

- Install: `uv sync --dev`
- Test: `uv run pytest`
- Lint: `uv run ruff check .`
- Type-check: `uv run mypy src`
- Exercise the CLI: `uv run repo-template --help`

## Design rules

- Keep the public CLI small: `new`, `update`, `check`, and `globals`.
- Updates must be idempotent and must not overwrite unrecognized user changes.
- A clean `check` means `update` has nothing to do.
- Keep project-specific instructions in generated `AGENTS.md`; keep reusable workflows in global skills.
- Never copy Claude credentials, history, caches, or machine state into this repository.
- Add tests for any change to rendering, update conflict handling, or symlink behavior.
- Every skill is recorded and licensed: vendored ones in the lock (and byte-identical to it,
  except the frontmatter fields an override changes), local ones in
  `.agents/skill-sources.json`. Run `repo-template globals` after catalog changes; it records
  overrides and, once the catalog is clean, regenerates the README catalog and notices.

## Safety invariants

- Existing unrecognized content is preserved.
- Replaced global files are backed up before symlinks are installed.
- `~/.claude` itself is never symlinked; individual skills are, and the portable settings are
  merged into `~/.claude/settings.json` without overwriting entries changed on the machine.
- Generated repositories never commit `.agents`, `.claude`, `.codex`, `.env`, or private keys.
- Hooks in the portable settings always exit 0, so they can never block a session.
- MCP servers are keyless and read-only, defined once in `.agents/mcp-servers.json`, and each
  denied tool is denied in both clients. repo-template never writes approval settings
  (`enableAllProjectMcpServers`, `enabledMcpjsonServers`) or Codex `[projects]`, trust,
  sandbox or approval settings, and an MCP entry changed by hand is kept.
