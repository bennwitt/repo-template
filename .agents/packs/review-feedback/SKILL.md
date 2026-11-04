---
name: review-feedback
description: Evaluate incoming code-review findings, implement valid fixes and explain evidence-backed disagreements. Use when asked to address review or PR feedback, rather than to perform the initial review.
---

# Address review feedback

Read the requested review scope, requirements, relevant code and the complete findings. Treat
findings as claims to verify, including those from another agent. A review request authorizes
analysis; apply fixes when the task includes addressing them. Existing authorization persists.

## Triage against the code

For each actionable finding, identify its location, triggering input, expected behavior and
consequence. Reproduce it or inspect the relevant contract. Distinguish a demonstrated defect,
a design preference, a duplicate, an out-of-scope suggestion and an item awaiting evidence.
Test the reviewer's proposed fix against compatibility, callers and existing project decisions.

An unclear item blocks only the work that depends on its answer. Ask a concrete question while
continuing understood, independent fixes. When a suggestion conflicts with settled requirements,
explain the conflict with evidence instead of silently changing the requirements. Mark unavailable
verification as unavailable; neither confidence nor a reviewer's authority proves correctness.

## Fix and verify

Prioritize security/correctness blockers and dependency order. Group related fixes where they
share a cause; use focused checks that can catch the reported failure. Keep unrelated suggestions
out of the patch. Check the resulting diff for changed behavior beyond the finding.

Recheck the affected behavior after a fix and complete required repository checks. Earlier
results remain usable for unchanged contents and relevant inputs; record what changed when
rerunning. A second reviewer should inspect substantial fixes when available and authorized.
An iteration limit bounds effort, not correctness: report unresolved serious findings explicitly
and do not label the work clean merely because the limit was reached.

## Report disposition

Return each finding as fixed (with location and verification), rejected (with technical evidence),
deferred (reason and remaining impact), or awaiting clarification/evidence. State any important
unverified boundary. Keep the response proportional to the review; a small patch needs a short
account, not a new tracking system. Posting replies, changing tickets, committing and merging
follow the task's existing scope and authorization.

Adapted from obra/superpowers `receiving-code-review` (MIT), with independent fixes allowed
while clarification is pending and verification tied to the actual contents. Provenance and
license text are recorded in the standards catalog.
