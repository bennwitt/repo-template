---
name: constraint-driven-development
description: Define measurable project quality constraints and detect weakened checks. Use when adding quality gates, setting coverage or performance budgets, or investigating skipped tests, suppressions, and lowered thresholds.
---

# Quality constraints

Read the project's existing policies, CI, commands, exceptions and current measurements first.
Extend their authoritative location. Use `CONSTRAINTS.md` only when the project needs a new
home for these decisions; keep commands in the existing scripts/configuration and link to them.

## Establish the contract

Ask only for choices not already settled: dimensions that matter, blocking versus advisory
checks, target versus measured baseline, and acceptable execution cost. Suggest defaults from
current evidence. Existing task authorization and accepted choices carry forward.

For each chosen dimension record:

| Field | Required content |
| --- | --- |
| Scope | Files, changed lines, endpoint, workload or deployment being measured |
| Rule | Threshold/direction, unit, rationale, and tolerance for measurement noise |
| Mechanism | Existing command/config that produces a verdict, including prerequisites |
| Timing | Local edit, task completion, CI or runtime environment; expected cost |
| Ownership | Owner and review date; exceptions have scope, reason and expiry |

Measure before inventing numbers. On legacy projects, a ratchet can hold today's value while
new work improves it. Repeated measurements establish noise; don't ratchet on one lucky run.
An unavailable tool or missing runtime URL is an unverified constraint, never a passing gate.

## Wire the checks

Reuse the project's tools and dependency manager: uv and ruff for this baseline, existing
equivalents elsewhere. Add only tools needed for the agreed dimensions. Put fast deterministic
checks close to edits; expensive mutation, security and browser checks belong at task end,
CI or a preview deployment. Reuse coverage output from the test run instead of running it twice.

For coverage, distinguish changed-line coverage from whole-project coverage. For performance,
specify the workload and percentile. For accessibility, record the automated checks plus manual
keyboard/focus testing needed for the UI. Automated checks do not establish full compliance.
Keep secret scanners in redacted mode and report locations, never credential values.

Agent-session hooks in this baseline always exit zero. Put blocking gates in project checks,
pre-commit or CI, not agent-session or pre-push hooks. Keep `CLAUDE.md` as `@AGENTS.md` when it
is a pointer; put any policy pointer in `AGENTS.md` once.

## Check the checks

Review the complete task diff, including staged, unstaged and relevant untracked files, for:

- lowered thresholds, removed jobs, changed exclusion scopes or weakened assertions;
- deleted/skipped tests and new suppression comments;
- stubs, swallowed errors, or exceptions added to make the current change pass.

These are review signals, not automatic proof of misconduct. A justified deletion, suppression
or exception needs a documented reason and equivalent protection where applicable. Compare
against the agreed base and inspect the actual behavior rather than counting tokens with regexes.

Finish by running the chosen checks and recording measured values, failures and unavailable
checks. Validate a failing example for any new gate so a command that silently does nothing
cannot be mistaken for enforcement. Writing a policy alone does not enforce it.

Adapted from Addy Osmani's `constraint-driven-development` (MIT), with project-tooling and
nonblocking session-hook requirements preserved. Provenance is in the standards catalog.
