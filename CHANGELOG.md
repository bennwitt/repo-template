# Changelog

## 0.2.0 - 2026-10-01

- Generate `GLOSSARY.md` (terms only) instead of `CONTEXT.md`, following the mattpocock skills'
  rename; Purpose and Boundaries move into the generated `AGENTS.md`. `update` lists an existing
  `CONTEXT.md` for a manual `git mv` instead of renaming a project-owned file, so existing
  repositories exit with `2` until they migrate.
- `check` is now a true dry run of `update`: it reports the Git hook path and `uv.lock` too, and
  accepts `--no-hooks` and `--no-lock`.
- `globals` removes links to deleted skills, keeps the `.claude/skills/` mirror in sync, and
  rejects an invalid `--standards-root` or `AI_DEV_STANDARDS`.
- Record skill receipts through Claude Code hooks for repositories with `.ai/receipt-policy.json`.
- Raise the baseline's `uv_build` pin to match this repository, and test that the two stay in
  sync.
- Commit `.agents/.skill-lock.json`, update nine mattpocock skills and `langgraph-fundamentals`,
  and remove `knowledge-graph-etl`, `swarm`, `setup-pre-commit` and `scaffold-exercises`.

## 0.1.0 - 2026-09-17

- Add safe `new`, `update`, `check`, and `globals` workflows.
- Add a Python/uv repository baseline derived from BidCore.
- Add portable Codex and Claude skill/settings synchronization.

