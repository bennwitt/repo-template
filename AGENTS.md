# Repository guide

This repository owns the standard used to create and update other repositories.

## Purpose

`repo-template` is the single maintained source for repository engineering defaults and portable
AI-development configuration across machines. Domain terms are defined in `GLOSSARY.md`.

## Boundaries

The CLI creates and updates Python/uv repository scaffolding and installs global symlinks. It does
not create GitHub repositories, push commits, copy secrets, or overwrite conflicting
project-owned files.

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

## Safety invariants

- Existing unrecognized content is preserved.
- Replaced global files are backed up before symlinks are installed.
- `~/.claude` itself is never symlinked; only portable settings and individual skills are.
- Generated repositories never commit `.agents`, `.claude`, `.codex`, `.env`, or private keys.
- Hooks in the portable settings always exit 0, so they can never block a session.
