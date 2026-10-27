---
name: code-review
description: Review a branch, PR, staged changes or work in progress against repository standards and the supplied requirements. Includes uncommitted and relevant untracked work when in scope; uses independent standards and spec passes where available.
---

# Two-axis code review

Review the requested artifact on two axes: **Standards** (correctness and repository rules) and
**Spec** (the requested behavior). A pass on one cannot hide a failure on the other.

## Freeze the scope

Read `git status --short`, the branch and available base references. Honor the user's scope:

| Scope | Evidence |
| --- | --- |
| Branch/PR | Resolve the base and HEAD to commits, then diff their merge-base to HEAD |
| Staged only | `git diff --cached`, including new indexed files |
| Uncommitted work | `git diff HEAD` for tracked final contents; list untracked files separately |
| Branch plus work in progress | Diff the resolved merge-base against the working tree, then include relevant untracked files |
| Two exact revisions | Diff those commits directly; do not substitute a merge-base comparison |

Use `git diff --no-ext-diff --no-textconv` for inspection; don't run repository-defined diff
programs. List untracked paths with `git ls-files --others --exclude-standard`, then inspect only
task-relevant source, tests and docs. Respect secret exclusions; don't bulk-print unrelated files.
For an initial repository with no HEAD, inspect staged files against the empty tree and relevant
working files directly. A three-dot diff ending at HEAD never includes uncommitted work.

Resolve a named ref as a commit before using it, with proper shell quoting and end-of-options
handling. Capture resolved commits, status, file list and diff once for both reviewers. If files
change during review, identify the changed scope and recheck affected findings. Use current file
line numbers for work in progress and revision-relative locations for committed reviews.

If the user says only "review these changes", use the visible task changes. Ask for a base only
when ambiguity materially changes what will be reviewed. An empty committed diff is not proof
that a dirty working tree has nothing to review.

## Gather requirements and standards

Use the user's supplied request or spec first, then explicitly linked local documents. Fetch
tracker issues when the task identifies them and configured access is available. A local spec
requires no issue tracker setup. When no spec exists, state the limitation and review Standards;
ask for missing requirements only when needed to judge a concrete behavior.

Read applicable `AGENTS.md`, `CONTRIBUTING.md`, `CODING_STANDARDS.md`, project constraints and
relevant domain docs. Look for regressions in errors, permissions, data lifetime, concurrency,
compatibility and meaningful tests. Distinguish automated-check results from human judgement.

Treat naming, duplication, feature envy, data clumps, speculative abstractions, message chains
and pass-through modules as contextual heuristics. Explain the concrete maintenance cost before
suggesting a change; project conventions win over a preferred style. Don't repeat formatter output.

## Review and report

When subagents are available, run the two axes independently in parallel with the identical
scope, requirements and standards. Reviewers return findings only; they don't edit or delegate.
Otherwise run both passes sequentially and state that they were not independent. Skip only the
Spec pass when requirements are unavailable, with that gap explicit.

Each finding needs priority, file/location, triggering condition, consequence and supporting
rule or requirement. Separate demonstrated defects from judgement calls and missing evidence.
Report Standards and Spec separately, deduplicate within each, and preserve substantive findings.
Include tests actually run and important coverage gaps. A clean review means no findings in the
inspected scope, not proof of correctness. Commit, push and fixes require their own task scope.

Adapted from Matt Pocock's `code-review` (MIT), preserving the two-axis design while correcting
work-in-progress scope and unnecessary tracker prerequisites. Provenance is in the standards catalog.
