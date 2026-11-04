# Resume substantial work reliably

Use a durable record when a task has multiple dependent stages, delegated work or a likely
context interruption. Small edits can use the conversation. Reuse an existing plan/progress
location; otherwise choose a task-specific ignored workspace or temporary directory outside
tracked content. State its path. For personal adoption, use a location that changes no visible
project files. Never collect credentials or private session transcripts in this record.

## Record identity and progress

Keep one record per task with:

- task/spec/plan path plus a content hash or revision; repository, worktree, branch and base;
- accepted scope and authorization, decisions and their consequences;
- task IDs, dependencies, affected interfaces/files, and ownership for concurrent workers;
- completed outputs, actual commit IDs or uncommitted content fingerprints;
- verification commands, tested contents, relevant inputs/environment, results and limits;
- unresolved review findings, blockers and the next useful action.

A compact Markdown table and notes are sufficient. Update after meaningful completed units
and before handoffs; do not create a bookkeeping step for every tool call. A worker's brief
names its requirements, interfaces, constraints, expected observations and allowed side effects.

## Resume by reconciling evidence

Read the record, current plan, Git status/diff and recorded commits. Confirm repository/worktree
identity and whether plan contents or prerequisites changed. A matching filename or task number
is insufficient: verify the recorded output still exists and satisfies current requirements.
Reopen only invalidated work; preserve completed work and unrelated user edits. Distinguish
uncommitted verified work from committed work instead of repeating either after compaction.

For interrupted work, inspect partial output before retrying actions. Confirm external actions
from authoritative state before repeating them. Record significant plan corrections and continue
within existing authority. Ask only when a material unresolved decision or new authorization
is required. If isolation fails, preserve the active checkout and resolve access or use another
isolated location; do not fall back to editing unrelated staged work.

## Finish with evidence

Associate each claim with the check that proves it: tests for exercised behavior, compilation
for a build, requirement review for scope, and environment-specific evidence for deployment.
A passing subset proves that subset. Reuse passing evidence when tested contents and relevant
inputs/environment remain valid; rerun affected checks after changes and all policy-required
checks. Another message alone does not invalidate evidence.

Keep important decisions and unresolved findings in the final report or project-owned record.
A review budget limit never resolves a defect. Remove only scratch/worktrees created for this
task after checking for unique uncommitted/untracked work and following task authorization;
a directory's name does not prove ownership. Retain recovery records needed for open PR work.

Adapted from obra/superpowers execution, resumption and verification guidance (MIT); source
paths and reviewed revision are recorded alongside the owning skills in the standards catalog.
