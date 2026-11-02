# Agent workflow choices

This file belongs to the project. Adapt it to the team's workflow; baseline updates create it
when missing and preserve edits. Skills are available after machine setup; domain skills require
a selected pack or individual selection. Invoke skills by name using the host's supported syntax.

## Equip the project with relevant skills

Before substantial implementation, or when the stack or task needs a missing capability, use
the `repo-template` skill and CLI to review available packs and individual skills. Match choices
to the project's dependencies, architecture and requested work; reuse installed skills first.

1. **Discover.** Run these read-only commands from the repository root:

   ```bash
   repo-template globals --list packs
   repo-template globals --list skills
   repo-template globals --list --repo .
   repo-template globals --list --json
   ```

2. **Choose.** Add only useful missing selections. A pack brings related skills and its MCP
   servers; an individual skill brings its supporting files without siblings or pack MCP servers.
   Preserve existing selections and the recorded adoption profile. For first adoption, follow
   the `repo-template` skill: personal for one person's use in a team repository, packs-only for
   another stack, or the full Python/uv baseline where appropriate.
3. **Preview and apply.** Use explicit flags for agents; for example, when delivery guidance
   and code simplification are relevant to the task:

   ```bash
   repo-template check . --pack delivery --skill code-simplification
   repo-template update . --pack delivery --skill code-simplification --no-input
   repo-template check .
   ```

   Inspect the preview before applying within the user's authorized scope. A full-profile
   update also reconciles baseline files. `check` can exit 1 for planned changes; inspect errors
   as well. Resolve reported errors or preserved conflicts using the `repo-template` skill.
   Completion means the final check prints "Standards are current." and the Git diff contains
   only intended changes; personal adoption must leave Git status unchanged.
4. **Use.** Read the selected skills' `SKILL.md` instructions before applying them. If the host
   has not refreshed its skill list, start a fresh agent session to discover the new skills.

`repo-template update . --select` is the interactive picker for a human at a terminal.
If the CLI or machine catalog is unavailable, report the setup needed and continue with available
skills where possible. Machine setup and upstream catalog upgrades are separate from project
selection; follow the user's authorization for them.

For MCP development, start with `mcp-developer` in the `mcp` pack: it routes Python,
TypeScript, compatibility and security work to the specialist skills. Read the project's locked
SDK versions first; skill installation does not authorize an application migration. Use the
standards repository's development baseline and executable MCP fixtures when changing examples.
Format only project-owned files, never recursively through installed skill symlinks.

## Choose the work, then the workflow

| Work | Preferred skills | Availability |
| --- | --- | --- |
| Clarify requirements | grilling, to-spec | global |
| Break an agreed spec into tasks | to-tickets | global |
| Implement an agreed scope | implement; implement-spec for a task graph | global |
| Test behavior or diagnose a failure | tdd, diagnosing-bugs | global |
| Review requirements and standards | code-review | global |
| Simplify or retire code | code-simplification, deprecation-and-migration | dev-workflows pack |
| Define quality gates | constraint-driven-development | delivery pack |
| Verify versioned APIs | source-driven-development | delivery pack |
| Measure performance | performance-optimization | performance pack |
| Instrument a feature | observability-and-instrumentation | sre pack |
| Design retries and API compatibility | api-and-interface-design | api pack |
| Assess release readiness | shipping-and-launch | delivery pack |

Use one implementation/testing workflow for a task. Add focused domain checks when relevant;
don't run competing lifecycle routers. Small changes do not require every phase. Preserve the
project's test seams and prior decisions instead of reopening settled questions.

For reviews, state the scope: committed branch, staged changes, uncommitted work, or branch plus
work in progress. Include relevant untracked files in a working-tree review. A local spec or the
user's request can supply requirements without an issue tracker. Report unavailable evidence.

## Configure only what is missing

`setup-matt-pocock-skills` configures an already installed workflow. Use it when tracker-dependent
work needs missing conventions in `docs/agents/issue-tracker.md`, `triage-labels.md` or `domain.md`.
Local Markdown is supported; a remote is not required for local work. Ordinary tests, debugging
and review of a supplied spec do not require setup. Read existing conventions first.

Keep shared project instructions in `AGENTS.md`. When `CLAUDE.md` contains `@AGENTS.md`, retain
that import stub and put new guidance in AGENTS, including when a skill suggests editing CLAUDE.
Respect seed-file ownership and existing glossary/ADR paths.

## Execution and evidence

Skills describe procedures; the user's task and repository rules determine authority to commit,
push, open or merge PRs, change trackers, deploy or delete data. Prior authorization persists.
Readiness is a scoped assessment, not deployment permission. Keep agent-session and pre-push
hooks nonblocking; enforce project quality gates in checks, pre-commit or CI.

Choose installed tool versions and the project's dependency manager. Read version-sensitive
official documentation when needed. Measure performance before claiming gains; separate source
hypotheses, local test evidence and production observations. A recreated schema is not restored
data: destructive migrations need a tested recovery or forward-repair plan.

Advanced skills such as implement-spec, wayfinder and loop-me have larger orchestration and
external-effect scopes. Use them intentionally with bounded work. The upstream in-progress
skills claude-handoff, loop-me, setup-ts-deep-modules, writing-beats, writing-fragments and
writing-shape are experimental; their availability is not a recommendation to use them by default.
