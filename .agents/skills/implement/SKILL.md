---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

If the user passes a ticket reference, fetch it from the issue tracker and state its title before starting. If the reference is ambiguous, ask.

For substantial or interrupted work, read [execution-record.md](references/execution-record.md)
for task identity, durable progress and evidence-based resumption. Reuse existing scope and
authorization; small edits do not need a ledger.

Call the Skill tool with "tdd" where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, call the Skill tool with "code-review" to review the work.

Commit when requested or part of the established task workflow. Preserve unrelated user work.

Adapted from Matt Pocock (MIT), with execution-record guidance derived from obra/superpowers
(MIT). Both sources and their reviewed revisions are recorded in the standards catalog.
