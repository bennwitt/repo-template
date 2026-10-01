# Changelog

## 0.3.0 - 2026-10-01

- Fix CI: `astral-sh/setup-uv` stopped publishing a floating `v10` tag, so every run failed to
  resolve it. Actions are now pinned to commit SHAs with version comments, and checkout no
  longer persists credentials. A test keeps workflow actions SHA-pinned.
- Replace the PR template with type-of-change and areas checklists, action-and-outcome
  verification steps, the quality checks, and a risk and rollback section.
- Skill packs: domain skills (`langchain`, `agent-evals`, `gradio`, `knowledge-graph`,
  `typescript`) load only in repositories that opt in with `new`/`update --pack NAME`.
- Skill overrides: `.agents/skill-overrides.json` keeps local frontmatter edits to vendored skills
  across `npx skills update`; used to narrow seven over-broad or over-long descriptions.
- `project_owned` in `.repo-template.json` lets a repository keep its own version of a managed
  file without `update` exiting `2` forever.
- Add a `repo-template` skill, and the `uv`, `ruff`, `supply-chain-risk-auditor`,
  `property-based-testing`, `github-actions-hardening`, `skill-scanner` and `pr` skills. Every
  vendored skill except the local `knowledge-graph-extraction` now has a recorded source.
- File policies move into `policies.py` behind one `decide` interface; the manifest records
  hashes only for managed files. The shared marker-block merge no longer expands backslash
  sequences in ignore rules.
- This repository passes its own `check`, enforced by a test. The baseline's smoke test now
  compares `__version__` with package metadata instead of hard-coding `0.1.0`.

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

