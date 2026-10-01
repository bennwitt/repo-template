# Changelog

## 0.4.0 - 2026-10-01

- `update` resolves discrepancies itself. In a terminal it shows a diff for each file that differs
  from the baseline and asks: use the baseline, keep yours, merge change by change, always keep
  yours, or skip. A file under an old name (`CONTEXT.md`, a `CLAUDE.md` holding the guide) can be
  moved with `git mv`, followed by a list of lines still mentioning the old name. Decisions apply
  as they are made. Without a terminal, or with `--no-input`, `update` lists the files as before.
- "Keep yours" and merged results are recorded as accepted differences in `.repo-template.json`
  (the file's hash and the baseline's), so `update` asks again only when the baseline's version
  changes. "Always keep yours" adds the file to `project_owned`.

## 0.3.1 - 2026-10-01

Found by adopting the baseline in bidcore, which it didn't generate:

- `update` added `[tool.ruff]` (line length 100) beside an existing `[tool.ruff.lint]`, which made
  90 more files fail `ruff format --check`. Tool tables are now added only for tools the project
  doesn't configure at all.
- `update` created an empty `src/<package>/`, a smoke test for it and a strict `[tool.mypy]`
  naming it, in a repository whose code sits directly in `src/`. A flat layout is now kept.
- `update` created a generic `AGENTS.md` beside a `CLAUDE.md` holding the real guide, so Codex
  read a placeholder. It now reports `CLAUDE.md` for a move into `AGENTS.md` instead.
- With no description in `pyproject.toml`, the fallback used the checkout directory's name rather
  than the project's.
- The skill receipt hook reads the older `log_path` spelling, so a policy using it no longer
  writes receipts to an unignored file.
- The `repo-template` skill covers adopting a repository: deciding each preserved managed file,
  moving `CLAUDE.md`, and repointing references after renaming `CONTEXT.md`.

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

