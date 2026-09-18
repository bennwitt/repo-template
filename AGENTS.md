# Repository guide

This repository owns the standard used to create and update other repositories.

## Commands

- Install: `uv sync --dev`
- Test: `uv run pytest`
- Lint: `uv run ruff check .`
- Type-check: `uv run mypy src`
- Exercise the CLI: `uv run repo-template --help`

## Design rules

- Keep the public CLI small: `new`, `update`, `check`, and `globals`.
- Updates must be idempotent and must not overwrite unrecognized user changes.
- Keep project-specific instructions in generated `AGENTS.md`; keep reusable workflows in global skills.
- Never copy Claude credentials, history, caches, or machine state into this repository.
- Add tests for any change to rendering, update conflict handling, or symlink behavior.

