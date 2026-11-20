---
name: seventy-two-percent-plan
license: MIT
description: "Plan a solution to 72%: solid and stable for one use case, with the one-way doors settled and the rest deliberately left open. Neither day-0 enterprise architecture nor a throwaway. Use when starting a project or feature, asked how much to design, or a plan is drifting toward either extreme. Writes a one-page plan."
---

# The 72% plan

A **72% plan** settles the decisions that are expensive to reverse and deliberately leaves the
rest to be learned while building. It is not the 100% plan (every variation an enterprise will
ever meet, designed on day 0), nor the 25% plan (a hack nobody will keep), nor a 50% plan that
hedges everything. The result is simple, functional and stable-ish: it serves one use case well,
can take some downtime, treats its data as disposable, and carries the lessons a larger team
needs if they later harden it into a slow, steady enterprise system.

The plan is one page. Planning is done when the stop rule below holds; everything else is a
two-way door and gets the boring default.

## Steps

1. **Read what exists.** The repository, its `AGENTS.md`, `GLOSSARY.md`, any prior plan or ADR,
   and the user's words. Settled decisions stay settled; ask only about the one-way doors below
   that nothing answers.
2. **Fix the frame.** One sentence each: the problem, the single use case, who uses it. Then
   the **non-goals**: at least three things this will not do, named so nobody designs for them.
3. **Set the appetite.** Fixed time, variable scope (Shape Up). State the budget in days or
   weeks and cut scope until the frame fits inside it. The appetite never grows to fit the scope.
4. **Sort the doors.** List every decision, then split it with
   [references/one-way-doors.md](references/one-way-doors.md): a **one-way door** is settled now
   with a reason; a **two-way door** gets the boring default and a one-line note that it is
   reversible. More than about five one-way doors means the frame is too big; go back to step 2.
5. **Choose boring.** Every choice comes from what the team already runs. One new technology
   per project at most, named as the innovation token with the reason it earns it.
6. **Declare the data disposable.** Default: every store is rebuildable from its source, so a
   schema change is drop, change, reload. Write the reload command into the plan. Name any
   precious data (cannot be re-fetched, legally retained, hand-entered) explicitly; only that
   gets migrations and backups.
7. **State the reliability target.** The downtime tolerance in plain words, restart-on-failure
   as the recovery model, and the three failure modes handled: bad input, a dependency down,
   a restart mid-work. Everything else surfaces as an error with context, not a retry tower.
8. **Define the walking skeleton.** The thinnest end-to-end path that passes through every
   one-way door and runs in the target environment. It is the first deliverable and should
   exist within the first quarter of the appetite.
9. **Write the deliberately-skipped list and the shortcuts.** What the enterprise version
   would have and this one will not, each with its add-when trigger, from
   [references/skip-list.md](references/skip-list.md); then the **rabbit holes**, known risks
   each patched with a line or two; then the **shortcuts** taken on purpose, each with its
   expected interest and the moment to pay it. Skipped on purpose is not forgotten.
10. **Sketch the hardening path.** Three to five lines on what a larger team would change first
    if they adopt this: which two-way doors they would revisit, which skipped items come first,
    what the precious data would be then. This keeps the lessons without building them.
11. **Apply the stop rule.** The plan is done when every one-way door has a choice and a
    reason, the non-goals and skipped lists exist, the data is declared, and the skeleton is
    defined. Stop there. Two-way doors are not planned; they are decided while building.
12. **Write the plan** from [references/plan-template.md](references/plan-template.md), one
    page, where the project keeps its documents (`docs/plans/<name>.md` when nothing exists).
    End it with what is **left to the builder**: the two-way doors and the details the plan
    does not decide. Hand it to the task-breakdown or implementation workflow; the plan is the
    brief.

## What keeps 72 from sliding to 25

- Tests cover the skeleton path and each one-way door's contract; nothing else is required.
- The reload command exists and is run once, which is the proof the data is disposable.
- The non-goals live in `AGENTS.md` or the README, where the next person finds them.
- A pre-mortem (`the-fool`) when the appetite is more than a few weeks or others depend on it.
- Pivoting means rerunning this skill on the new frame, not patching the old plan.

## What keeps 72 from growing to 100

- A request to handle a case outside the frame is answered with the non-goals and the
  skipped list, and either the trigger fires (add it now) or it does not (write it down, move on).
- A new abstraction needs two concrete callers in the current scope before it exists.
- Configuration, plugin points and feature flags are two-way doors: add them when the second
  value appears.

The principles behind each step, with their sources, are in
[references/principles.md](references/principles.md).
