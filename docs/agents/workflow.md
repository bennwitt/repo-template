# Agent workflow choices

This file belongs to the project. Adapt it to the team's workflow; baseline updates create it
when missing and preserve edits. Skills are available after machine setup; domain skills require
their pack. Invoke skills by name using the host's supported syntax.

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
