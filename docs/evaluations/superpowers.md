# Superpowers evaluation — 2026-11-03

## Recommendation

Use Superpowers as a selectively adapted source, not as a replacement for our workflow or an
additional always-on framework. Keep the existing Pocock-based specification, task graph,
implementation, testing and two-axis review routes. The best additions are review-feedback
handling and a stronger way to evaluate skills; the best improvements to existing workflows
are execution recovery records, explicit completion evidence and focused debugging techniques.

The original assessment below is source-based, not a comparative model benchmark. The
subsequent authorized implementation is recorded in the implementation section. No upstream plugin,
hook, companion server or helper was installed or run for this review.

## Reviewed revision and method

- Source: [obra/superpowers](https://github.com/obra/superpowers).
- Reviewed commit: [22f0b463e7a5e579904dd6211a520321035526f7](https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7),
  release **7.0.2**, dated **2026-11-03**. The commit's timestamp is
  `2026-11-03T14:17:07-08:00`; the version is recorded in the
  [plugin manifest](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/.claude-plugin/plugin.json).
- License: [MIT, copyright 2025 Jesse Vincent](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/LICENSE).
- Scope: all **15 skill main files**, relevant reviewer/executor/testing/debugging references,
  and comparison with our installed `tdd`, `diagnosing-bugs`, `code-review`, `implement`,
  `implement-spec`, `to-spec`, `to-tickets`, `writing-for-agents`, delivery skills and
  [agent workflow guide](../agents/workflow.md). Installation/security inspection is recorded below.
- Context-size observation: the 15 main files contain **22,199 whitespace-delimited words** at
  this commit, excluding supporting files. This is source volume, not runtime token usage:
  hosts normally disclose only selected bodies, while the router increases how often they load.

The [release notes](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/RELEASE-NOTES.md)
report recent prompt comparisons and harness fixes. Those are upstream's measurements, not
our replicated results. The same-day release deserves a pinned local trial before adoption;
the development-package seven-day policy should not be silently generalized into a new skill rule.

## Complete skill decision matrix

Every source link below is pinned to the reviewed revision. “Adapt” means a maintained local
derivation or attributed reference, not an unchanged vendor import. The matrix records the initial recommendation; the implementation section records adopted changes.

| Upstream skill | Existing route | Decision and concrete reason |
| --- | --- | --- |
| [brainstorming](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/brainstorming/SKILL.md) | `grilling`, `to-spec`, `prototype` | **Keep current route; borrow selected techniques.** It now reads existing context first, asks only consequential questions, sizes design documents and permits a quick-task/opt-out path. But its broad creative-work trigger, approach/design approval sequence and mandatory transition to its planner would reopen already authorized work. Keep intent, anti-goals and the builder-check rubric as optional requirements checks. |
| [diagnosing-superpowers](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/diagnosing-superpowers/SKILL.md) | No direct equivalent | **Defer.** It addresses agent-session cost, repeated work and evidence gaps, which are useful concerns, but requires seven analyst dimensions, reads private transcripts and is explicitly a Superpowers report workflow that forbids fixing the skill it investigates. A future bounded, opt-in session audit would need a separate purpose and privacy contract. |
| [dispatching-parallel-agents](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/dispatching-parallel-agents/SKILL.md) | `implement-spec`, research and review delegation | **Adapt a short reference; no new router.** Independent problem domains, self-contained briefs and integration checks are useful. Preserve task-graph dependencies, file ownership, host concurrency limits and explicit delegation scope. Two failures are not evidence that they are independent. |
| [executing-plans](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/executing-plans/SKILL.md) | `implement` | **Adapt recovery/evidence mechanisms into existing implementation guidance.** Per-plan ledgers, recorded decisions, exact verification expectations and continuous execution improve long tasks. The full skill also imports its planning format, helpers, TDD and finishing workflow; a second executor would compete with our existing route. Its prohibition on a second final review/fix pass must not override unresolved correctness findings. |
| [finishing-a-development-branch](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/finishing-a-development-branch/SKILL.md) | `repo-template`, `pr`, `shipping-and-launch`, task authorization | **Do not import.** Explicit PR-template use and preserving externally managed worktrees are good. An unconditional integration menu conflicts with our user's already-authorized commit/PR/merge workflows. Cleanup ownership inferred from directory names is insufficient, and generic `git pull` does not encode our fast-forward-only reconciliation. |
| [receiving-code-review](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/receiving-code-review/SKILL.md) | `code-review` produces findings but has little feedback-processing guidance | **Highest-priority focused addition, adapted.** Validate a finding against requirements and actual code, distinguish real defects from preferences, prioritize and verify fixes, and record evidence-backed disagreements. Remove the instruction to halt all fixes if one item is unclear; proceed with independent understood items. A compact `review-feedback` skill is justified if invoked separately from review; otherwise a reference under `code-review` is cheaper. |
| [requesting-code-review](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/requesting-code-review/SKILL.md) | Adapted `code-review` | **Keep current skill.** We already freeze scope and run Standards/Spec independently, including staged, unstaged and relevant untracked work. Upstream's basic SHA-to-SHA example and reviewer template do not cover that working-tree scope. Borrow small reviewer-brief details only where they improve our contract. |
| [subagent-driven-development](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/SKILL.md) | `implement-spec` | **Adapt selected orchestration references; do not replace.** Durable progress, exact task interfaces, concise reports and bounded review loops are useful. Upstream explicitly serializes implementation tasks and imports a large helper/tooling contract; our graph permits genuinely independent worktrees in parallel. Retain capacity controls and evidence without allowing a loop cap to turn unresolved serious defects into completion. |
| [systematic-debugging](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/systematic-debugging/SKILL.md) | `diagnosing-bugs` | **Keep incumbent; adapt selected references.** Our reproducible feedback loop, ranked falsifiable hypotheses, minimization, redaction and cleanup are stronger fits. Upstream adds useful backward tracing and condition-based waiting. Do not import the fixed three-failure architecture stop, blanket every-layer validation, or an unsafe path-prefix guard from its support material. |
| [test-driven-development](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/test-driven-development/SKILL.md) | `tdd` | **Keep incumbent and improve it selectively.** Both favor behavior and independent expected values. Upstream's test-quality reference adds an explicit “which realistic break does this test catch?” check. Its universal test-first mandate, delete-and-rewrite rule and permission gates for exceptions are poor defaults. Our incumbent's unconditional seam confirmation is also a friction point: reuse previously agreed seams rather than asking again. |
| [using-git-worktrees](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/using-git-worktrees/SKILL.md) | `implement-spec`, `repo-template` | **Adapt safe-isolation reference only.** Existing-worktree/submodule detection and honoring host-native isolation are useful. Generic `npm install`/`poetry install`, automatic ignore-file commits and an in-place fallback after a permission failure are unsuitable for our uv/locked-dependency and dirty-checkout rules. |
| [using-superpowers](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/using-superpowers/SKILL.md) | Existing agent discovery guide | **Exclude.** A one-percent applicability threshold and invocation before any reply or exploration create a competing universal router. It explicitly respects user instructions and excludes dispatched workers, but the default still encourages excessive activation. |
| [verification-before-completion](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/verification-before-completion/SKILL.md) | Agent workflow guide, `constraint-driven-development`, `shipping-and-launch` | **Adapt a completion-evidence contract into existing guidance.** Mapping each claim to a proving command and distinguishing tests, build, requirements and production readiness are useful. Replace freshness measured by the current message with freshness tied to revision, inputs and environment. Unchanged passing evidence should not trigger repeated full suites. |
| [writing-plans](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/writing-plans/SKILL.md) | `to-spec`, `to-tickets` | **Adapt execution-brief fields, keep task graph.** Exact interfaces, expected command outcomes and cross-task consistency checks improve handoffs. Store those in implementation briefs when needed, not every long-lived ticket: our tickets deliberately avoid brittle file/line/code duplication. Respect an already-approved plan instead of requiring a new planning/handoff gate. |
| [writing-skills](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/writing-skills/SKILL.md) | `writing-for-agents`, host `skill-creator`, existing evaluation reports | **Second focused addition candidate: adapted `skill-evaluation`.** The strongest contribution is controlled before/after behavior testing, realistic pressure scenarios and repeated samples. Keep authoring/progressive-disclosure guidance in existing skills. Do not import forced deletion of untested drafts, a full lifecycle for every prose edit, or compliance with the skill's preferred answer as the sole measure of quality. |

## Why this is a selective adoption

### Actual gaps worth filling

1. **Feedback handling.** Our review skill tells reviewers how to find and report defects; it
   does not give implementers a concise method for accepting, rejecting, splitting and verifying
   incoming suggestions. A separate narrow trigger can earn its discovery cost. Source:
   [receiving-code-review](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/receiving-code-review/SKILL.md).
2. **Skill behavior evaluation.** Existing reports document forward exercises, but the catalog
   does not expose a focused procedure for controlled comparisons, repeated trials and
   regression scenarios. Start with a no-guidance control, score task outcomes and unwanted
   actions, inspect variance, and keep holdout scenarios so rewriting the prompt does not merely
   overfit the tests. Upstream supplies useful controls/repetitions, but its pressure-test
   examples sometimes define success as obeying a deletion rule; that is not independent
   evidence of better engineering. Sources:
   [writing-skills](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/writing-skills/SKILL.md),
   [testing reference](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/writing-skills/references/testing-skills-with-subagents.md).
3. **Recovery across long executions.** Existing `implement-spec` uses context pointers and
   a task graph, but its main body does not define a durable, revision-bound record of completed
   work, decisions, test evidence and pending review findings. Keep this as an optional mechanism
   for long tasks rather than a workspace/helper requirement on short ones. Upstream's ledger
   checks identity by plan path; our adaptation should also verify plan content/version and
   recorded commits before skipping work after changes. Sources:
   [executor](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/executing-plans/SKILL.md),
   [resumption](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/references/resuming.md).

### Improvements to retain without importing another lifecycle

- Record completion evidence against the tested revision/content, command, relevant environment,
  outcome and coverage limit. Re-run when code, inputs or environment invalidate evidence, or
  repository policy requires it; do not rerun solely because a new message is being written.
- In task briefs, name consumed/produced interfaces and acceptance outcomes. Keep the spec as
  authority and record necessary plan corrections. Do not prescribe whole implementations when
  signatures, constraints and observable behavior suffice.
- For review loops, use focused rechecks of the fix and new breakage. A budget/cap can stop a
  costly loop, but unresolved correctness/security findings remain unresolved and prevent a
  clean-completion claim. Upstream's
  [fix-loop breaker](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/references/fix-loop.md)
  and [single final fix wave](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/subagent-driven-development/references/final-review.md)
  need this correction.
- Improve debugging with backward data-flow tracing and bounded waits for observable conditions.
  Preserve our incumbent's credential redaction, symptom-specific reproduction and cleanup.
  Sources: [root-cause tracing](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/systematic-debugging/root-cause-tracing.md),
  [condition waiting](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/systematic-debugging/condition-based-waiting.md).

### Incumbents are not perfect

Keeping a skill is a fit decision, not a blanket endorsement of every line. Current `tdd`
requires user confirmation before every new test seam; current `to-spec` and `to-tickets`
also have explicit confirmation stages. Prior authorization and already settled choices must
carry through these routes. `implement-spec` has aggressive reset/cleanup instructions that
should become explicit ownership and preservation checks in a future local adaptation.

Superpowers 7.0.2 is also more nuanced than a simple “too many approvals” label suggests:
brainstorming recognizes clear tiny tasks and permits an opt-out, while both executors require
continuous authorized execution without task-by-task check-ins. The incompatibilities are the
remaining hard lifecycle gates and overly broad triggers, not a lack of autonomous execution.

## Source-based scenario checks

These are manual instruction-path comparisons, not agent behavior trials. They identify what
must be tested before promotion; they do not establish success rates.

| Scenario | Source behavior that needs correction | Acceptance for our adaptation |
| --- | --- | --- |
| User supplies an approved plan and asks to implement, commit, PR and merge | Brainstorming/planning can request a fresh design/plan approval; finishing always offers a menu | Proceed on existing authority; ask only for a new material decision or genuine authorization gap |
| Six review items, one ambiguous and independent of the rest | `receiving-code-review` stops all implementation | Clarify that item while completing understood independent fixes |
| Full checks already passed on unchanged contents | Completion verifier requires a fresh command in the current message | Reuse valid recorded evidence; invalidate it only for a material change or required gate |
| Dirty team checkout, worktree creation fails | Worktree guide suggests working in place | Preserve staged/untracked work; obtain the needed sandbox access or another isolated workspace |
| Reviewer is asked to inspect staged and untracked work | Basic upstream review recipe uses only commit SHAs | Keep our exact scope model and include all relevant working-tree evidence |
| Long plan resumes after plan edits at the same path | Ledger names the plan file and marks task numbers complete | Check plan identity/version and actual commits before trusting completion markers |
| A safety guard accepts a sibling path sharing the temporary-directory prefix | `defense-in-depth.md` uses string `startsWith` for containment | Resolve paths and use component-aware containment; test symlinks and sibling prefixes |

The last source example is concrete: a normalized path such as `/tmp-other` starts with `/tmp`
but is not inside it. The documentation's
[environment guard](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/systematic-debugging/defense-in-depth.md)
also does not resolve symlinks. An isolated Node path-operation check reproduced the first
case: `normalize(resolve('/tmp-other/project')).startsWith(normalize(resolve('/tmp')))`
returned `true`, while the path is outside `/tmp`. This check ran no upstream helper and made
no filesystem changes. Do not copy the example as a filesystem safety boundary. Its assertion
that validation at every layer makes bugs impossible is not a guarantee we should repeat.

## Suggested adoption sequence

1. **Trial two narrowly scoped additions.** Prepare `review-feedback` and `skill-evaluation` as
   local MIT derivations. `review-feedback` can be an individual selection or a focused member
   of `dev-workflows`; `skill-evaluation` fits the existing `agent-evals` pack. If trial usage
   shows feedback handling is always reached through `code-review`, make it a reference there
   instead of adding a redundant skill entry.
2. **Improve existing guidance.** Add a short completion-evidence contract to the workflow
   guide/delivery references and optional ledger/brief/isolation references to implementation
   guidance. Add only the useful debugging/test-quality techniques. Keep current skill names
   and project selections; do not add a `superpowers` lifecycle pack.
3. **Prove benefit before replacing anything.** Run matched scenarios against incumbent-only,
   candidate-only and adapted guidance using the same model/environment. Score actual task
   correctness, unnecessary approval turns, missed working-tree files, unwanted Git changes,
   repeated checks, recovery after interrupted work and token/time cost. Include a small task,
   an already-approved task and a dirty-checkout task. Repeated samples and holdouts are needed
   before making superiority claims.
4. **Record provenance and ownership.** Copy the MIT license, record commit/tree/source paths,
   list companion inputs in `additionalPaths`, and classify changed bodies as local derivations.
   Update `.agents/skill-sources.json` decisions and the implemented selection in
   `docs/skill-evaluation.md` when adoption is chosen. Regenerate notices/catalog using a temporary home; test selected/full/packs-only/
   personal adoption and ensure upstream drift reports manual-review items for derived inputs.
5. **Publish separately after validation.** Update affected user/agent documentation and changelog
   with the actual selected behavior. Do not install upstream session hooks, a visual companion,
   transcript collection or runtime plugins as an incidental side effect of adopting text skills.

## Evaluation limits

The inspected source supports a clear best-fit recommendation, not a claim that Superpowers
performs worse on all models or tasks. Its release notes contain useful test reports but were
not replicated here. The snapshot's `docs/testing.md` points to an `evals/` directory that is
absent from the reviewed checkout, so this report does not treat a live evaluation campaign as
reproducible bundled evidence. No full agent benchmark, production rollout or plugin execution was part
of this evaluation. The initial evaluation changed only documentation. Subsequent catalog changes are recorded below;
machine globals and consumer selections were not changed by this implementation.

## Installation, runtime and scan evidence

The stock repository scanner was run against all **15 skill directories** at the pinned revision;
it returned zero pattern findings. Its script pass covers only direct `.py`, `.sh`, `.js` and
`.ts` children under `scripts/`, so that result does not cover all executable material. A second
pass called the same trusted scanner's `check_scripts` function explicitly on **13 additional
`.cjs`, `.mjs` and extensionless shebang files**, including hooks and helpers. This produced one
raw high-severity `exec()` match at `skills/brainstorming/scripts/server.cjs:540`. Manual inspection
shows an operator-supplied `BRAINSTORM_OPEN_CMD` launcher override, gated by opt-in browser
opening; it is shell execution to account for, not evidence of malicious behavior. The normal
platform launcher uses an argument array with `execFile`. Raw outputs are in the local temporary
review workspace `/tmp/superpowers-scan/`; they are not an installed package or a catalog record.

The review inspected the Claude session bootstrap, Codex manifest, SDD shell helpers, relevant
visual-server authentication/file-serving/launcher paths, and the skill instructions as source.
No upstream installer, hook, companion server, helper or live-model evaluation was executed.
This is a targeted source assessment, not a complete vulnerability audit of every harness adapter.

- **Bootstrap differs by host.** Claude's hook is synchronous (`async: false`) and injects the
  `using-superpowers` instructions at session start. The checked-in Codex plugin manifest has
  an empty `hooks` object. Avoid describing all host integrations as identical. The Claude
  script normally ends with `exit 0` and handles output errors, but that alone does not make a
  synchronous launcher satisfy repo-template's nonblocking-hook invariant.
- **The visual companion has real safeguards.** Its default bind is loopback; a generated
  32-byte random key authenticates HTTP and WebSocket access, key-bearing files use owner-only
  permissions, WebSocket origins are checked, and responses set `Referrer-Policy: no-referrer`.
  The implementation rejects symlink/hardlink assets in its file-serving path. These are useful
  protections, not a reason to describe it as an unauthenticated public server.
- **Telemetry is disclosed and opt-out.** Its branded image is loaded from `primeradiant.com`
  with the Superpowers version unless an opt-out environment variable is set. The inspected
  request does not add project or prompt content. Loading a remote image still contacts an
  external service; our selected adaptations do not need this runtime or network dependency.
- **Session diagnosis has a larger scope.** `diagnosing-superpowers` reads local transcripts,
  requires seven analyst dimensions, and can prepare redacted bundles. It has explicit gates
  before export and issue creation. Keep any future transcript-analysis capability separately
  invoked and bounded; catalog installation is not permission to collect or publish sessions.

Primary evidence: [Claude hook configuration](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/hooks/hooks.json),
[bootstrap](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/hooks/session-start),
[Codex manifest](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/.codex-plugin/plugin.json),
[companion source](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/brainstorming/scripts/server.cjs),
[telemetry disclosure](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/README.md#visual-companion-telemetry).


## Authorized implementation — 2026-11-03

- Add `review-feedback` to `dev-workflows` and `skill-evaluation` to `agent-evals`, each also
  individually selectable. Both are concise local MIT derivations; no upstream runtime is bundled.
- Retain `implement`, `implement-spec`, `diagnosing-bugs` and `tdd` names and placements, converting
  them to local adaptations. Add task identity and durable progress, verify recorded outputs
  before resuming, preserve unrelated work, and reuse settled authorization and test seams.
- Add focused backward-tracing/condition-wait guidance and test-sensitivity checks. Completion
  evidence in the workflow guide and release-readiness skill is tied to tested contents and
  relevant inputs/environment, with required repository checks preserved.
- Preserve primary Pocock/Addy attribution and track Superpowers companion inputs using
  `additionalSources`. Catalog validation, generated notices and upstream reports cover every
  recorded source; changed inputs remain manual-merge items.
- Keep the initial exclusions: no universal router, finishing menu, companion server, session
  bootstrap or transcript collector. Existing project workflow seeds remain preserved.

### Behavioral validation

Three independent agents exercised the new guidance in isolated synthetic workspaces. Each had
only the relevant skill/reference and task fixture; expected outcomes stayed with the parent.
These are single forward-use exercises, not an incumbent comparison or a general quality benchmark.

| Guidance | Challenge | Observed result |
| --- | --- | --- |
| `review-feedback` | Inclusive quota bug, an incompatible error-handling suggestion, and an ambiguous team-normalization request | Fixed the boundary with a failing-then-passing regression test; rejected the incompatible suggestion using the contract; isolated the unclear request. Parent inspected the artifact and reran all five tests successfully. |
| `skill-evaluation` | Three supplied pilot records with lower candidate costs, a lost unrelated file and a missing preservation check | Retained the incumbent; treated missing evidence as unknown and the deletion as failure despite self-reported success. Disclosed missing setup data and proposed controlled future trials without running additional calls. Parent inspected the report against the supplied records. |
| Execution record | Same plan path with changed contents, a stale completed marker and unrelated user notes | Detected the changed plan, added trimming and blank-name rejection, preserved the function signature and notes, and updated the record without commits or extra worktrees. Parent inspected the code and reran two tests covering eight cases. |

Temporary CLI exercises passed for full, packs-only and personal adoption: pack and individual
selection, listing, removal, retained individual selection after pack removal, and a clean repeat
check. Personal adoption left Git status unchanged. Static scans of all seven changed workflow
skills reported no findings; both new skill files passed the skill-creator validator. These scans
are bounded checks, not proof of safety.

The catalog records exact commits and copied-license hashes. Automated regression coverage checks
multi-source drift reporting, rejection of malformed provenance, and license integrity/notices.

### Repository validation and review

The full test suite, Ruff lint/format checks, mypy, catalog integrity and repository self-check
passed. Independent Standards and Spec reviews covered the working changes and this report.
Standards review found a crash when a secondary source used a non-string repository value;
a failing regression test reproduced it before the fix. Malformed records now remain review
items without breaking discovery reporting. No other actionable findings were reported.

Machine client configuration and consumer repositories were outside this implementation's
validation scope. Temporary-home checks skipped real client MCP installation; the three adoption
profiles exercised local skill links and selection reconciliation without a machine rollout.
