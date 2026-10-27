---
name: code-simplification
description: Refactor working code for clarity while preserving observable behavior. Use for a requested simplification pass, tangled control flow, duplication, or abstractions that obscure the changed code.
---

# Code simplification

Start with the requested scope, or recently changed code. Read callers, tests and project
conventions before editing. Use history when it explains a surprising constraint; a pattern's
age alone is not evidence that it should be removed.

1. State the behavior to preserve: outputs, errors, side effects and their order, mutability,
   concurrency, resource lifetime and public compatibility. Identify tests that observe it.
2. Pick one concrete source of complexity. Prefer a name, guard clause, removal of proven dead
   code, or consolidation at a real shared responsibility over introducing another abstraction.
3. Make a small change, run relevant behavioral tests, and inspect the diff. For a larger
   repetitive transformation, use a reviewed codemod and inspect representative edge cases.
4. Run the project's required checks once the pass is complete. Report the simplification,
   behavior evidence, and any equivalence you could not establish.

Keep behavioral changes separate from refactoring so each can be reviewed and reverted on its
own. Existing authorization determines whether to commit; this workflow adds none.

## Equivalence traps

- Removing `async` can turn a thrown error into a synchronous exception instead of a rejected
  promise. Removing `return await` can affect error handling, cleanup and stack traces.
- Replacing loops with comprehensions or maps can change evaluation order, eager/lazy behavior,
  duplicate-key handling or allocations. Check the contract before rewriting.
- Early returns can skip cleanup or logging. Check context managers, `finally`, locks and
  transactions, not just returned values.
- A wrapper may enforce permissions, normalize errors, provide instrumentation or form a useful
  test seam. Prove it has no responsibility before removing it.
- Editing a test to match a new result is evidence of a behavior change. Preserve the expected
  observations; a necessary test refactor must keep its coverage and assertions meaningful.

If a change fails checks, inspect the cause and undo only your own failed edit. Preserve other
work in the tree. A smaller diff or fewer lines is not a success criterion; clearer code with
the same contract is.

Adapted from Addy Osmani's `code-simplification` (MIT); provenance and reviewed upstream inputs
are recorded in `.agents/skill-sources.json` in the standards repository.
