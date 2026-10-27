# Forward evaluation of the local Pocock adaptations

Date: 2026-10-27. Drafts read from `/tmp/curated-skills/code-review/SKILL.md` and `/tmp/curated-skills/setup-matt-pocock-skills/SKILL.md`.

This is a forward execution by a reviewer separate from the draft author against controlled local fixtures. It checks whether the prescribed workflow can handle the concrete failure cases. It is not a blinded trial, repeated model evaluation or proof of general instruction adherence. No production repository files were changed, no tracker was contacted, and no upstream executable template was run.

## Case 1: branch plus staged, unstaged and untracked work

Fixture: `/tmp/pocock-behavior-fixtures-xuaqh637/review-mixed-changes`.
Base: `2e120a42501a6d6b5c18dc456907b6202f7eb4ec`.
HEAD: `daea4058f508c8a616a891ec1a78d9a0f9e6fb7c`.

Request: review the branch since the supplied base, including all current work, against local `spec.md`; do not set up a tracker.

Followed the draft's scope selection, resolved both revisions as commits, captured the merge-base, status and tracked diff once using `--no-ext-diff --no-textconv`, then listed relevant untracked source separately. Read the supplied spec and AGENTS instructions directly. The four agent slots were occupied, so the two review passes ran sequentially; they were not independent reviewer contexts.

### Observed coverage

| Change state | File | Upstream prescribed three-dot HEAD diff | Adapted procedure |
| --- | --- | --- | --- |
| Committed on feature branch | shipping.py | Included | Included |
| Staged modification | cli.py | Omitted | Included |
| Unstaged modification | calc.py | Omitted | Included |
| Untracked source | receipts.py | Omitted | Included |

The original procedure enumerated **1 of 4** changed source files; the adapted procedure enumerated **4 of 4**. No files were staged or changed to obtain that coverage. The fixture had no issue-tracker configuration, and none was requested or created.

### Standards pass

- **P1 — `receipts.py:2`: credential disclosure.** Calling `render_receipt` with an access token puts the token into returned receipt text. That makes the sensitive input part of the output rather than keeping it private. The local spec independently prohibits the same exposure; the draft's data-lifetime/security inspection also identifies it.

The remaining findings below are concrete requirement violations; there were no additional supported style or architecture findings in this deliberately tiny fixture.

### Spec pass

- **P1 — `receipts.py:2`: access token appears in receipt output.** The requirement forbids printing or returning the token. The synthetic probe returned `Order order-1, token synthetic-token`.
- **P2 — `calc.py:2`: unrequested discount.** `total_cents([1000, 250])` returned **1150**, while the supplied requirement expects **1250** with no explicitly requested discount.
- **P2 — `cli.py:2`: cents displayed as dollars.** `render_total(1250)` returned **`$1250`**, while the spec expects **`$12.50`**.
- **P2 — `shipping.py:2`: free shipping below the threshold.** `shipping_cents(1250)` returned **0**, while the spec expects **499** below a 5000-cent order.

Each defect was confirmed by executing only locally authored fixture functions with synthetic inputs. The review did not execute upstream skill scripts. Status was captured again at completion and matched the starting snapshot. No fixes or commits were made.

**Result:** pass for complete requested scope, local-spec handling, concrete findings and preservation of the reviewed work. The sequential fallback was exercised and disclosed. Parallel independence was not evaluated because no slots were available.

## Case 2: approved local setup with an AGENTS authority and CLAUDE stub

Fixture: `/tmp/pocock-behavior-fixtures-xuaqh637/setup-local-tracker`.

Starting state:

- `AGENTS.md` exists and contains a project-specific sentence that must survive.
- `CLAUDE.md` is exactly `@AGENTS.md\n`.
- `GLOSSARY.md` exists.
- There is no Git remote or existing workflow configuration.
- The request approves local Markdown, standard triage labels and a single glossary with `docs/adr/`.

Read the existing guide, pointer, glossary, remotes and installed triage availability. All choices were already resolved, so no intake questions were repeated. The draft's tracker/domain templates were copied from the pinned upstream checkout into the draft folder where not yet present, then used to create:

- `docs/agents/issue-tracker.md` using the local-Markdown operations;
- `docs/agents/triage-labels.md` using the default vocabulary;
- `docs/agents/domain.md` retaining the single-context layout;
- an `Agent skills` pointer block in `AGENTS.md` only.

The configuration records `.scratch/<feature>/spec.md` and one Markdown file per ticket, with no remote dependency. `docs/adr/` was created as the chosen location. Every new pointer resolves.

Verification:

- Original AGENTS content remains byte-for-byte at the beginning of the guide.
- CLAUDE remains byte-for-byte `@AGENTS.md\n`.
- `git remote -v` remains empty.
- No `gh` or `glab` command was run and no remote labels were created.
- A repeated pass reads and keeps the same choices; file SHA-256 values are identical before and after the second pass.

**Result:** pass for authorized local setup, correct guide ownership, no redundant questioning, no remote setup and repeatability.

## Limits and evidence artifacts

These fixtures target the two demonstrated integration defects. They do not cover a custom preexisting tracker document, a substantive CLAUDE-only project, a missing HEAD, concurrent file edits, ambiguous review scope, a real remote tracker or unavailable filesystem permissions. Those paths still require routine reasoning and further cases if changed.

Artifacts:

- `/tmp/pocock-behavior-fixtures-xuaqh637/manifest.json`: prompts, expected coverage and starting state.
- `/tmp/pocock-review-scope-snapshot.json`: resolved commits, status, source lists, diff, spec and standards used by both passes.
- `/tmp/pocock-review-execution-evidence.json`: actual/expected synthetic function outputs.
- `/tmp/pocock-setup-evidence.json`: file hashes for the first and second setup pass and ownership checks.

The outcomes support adopting these corrections. They do not establish that one author's entire collection is better than another's.

---

# Curated skill behavioral evaluation

Date: 2026-10-27. Evaluator: independent review agent, using the draft skills under `/tmp/curated-skills/`. No repository edits, deployments, browser sessions, database queries, or third-party scripts were run.

Method: two concrete fixture requests were answered by applying the relevant draft, followed by assessment against failure conditions chosen for each fixture. This is a single evaluator's prompted behavioral exercise, not a repeated model benchmark, a real runtime measurement, or a guarantee that every model will comply. The reviewer saw the draft and task context; this is not a blinded comparison with upstream.

## Case P1: Source-only web-performance audit

### Request fixture

> Audit the performance of this React product page and tell me whether it meets Core Web Vitals. I only have the source below; there is no running server, build output, trace, Lighthouse report, or field data. Please identify the highest-value next steps. Do not start a server or change files.
>
> ```tsx
> import Editor from './LargeRichTextEditor';
> import { ProductReviews } from './ProductReviews';
>
> export function ProductPage({ product, reviews }) {
>   return <main>
>     <img src={product.originalImageUrl} alt={product.name} />
>     <h1>{product.name}</h1>
>     <ProductReviews reviews={reviews} />
>     <section className="below-the-fold">
>       <Editor initialValue="" />
>     </section>
>   </main>;
> }
> ```
>
> The editor is needed only when a user chooses “Write a review.” The stylesheet and imported modules are not supplied.

### Response produced using the draft

This source is enough to identify candidates for measurement, but it does not establish whether the page meets Core Web Vitals. LCP, INP, CLS, transferred bytes, and parse/render costs are unavailable.

| Candidate | Source evidence | Proposed next step | What would validate it |
| --- | --- | --- | --- |
| Editor loaded before use | A static editor import and unconditional render, although the feature is only needed on user action | Evaluate deferring the editor import and render until review composition starts | Compare initial bundle/network and main-thread profiles; verify editor startup, focus, error handling, and first-use latency |
| Product image may transfer unnecessary bytes | URL is named `originalImageUrl`; no responsive source selection is visible | Inspect actual dimensions, formats, response bytes, and display size before choosing variants | Network evidence and matched LCP runs on a representative device/network; filename alone does not prove image size |
| Image space may be unreserved | No HTML width/height attributes appear | Check the missing stylesheet for a stable aspect-ratio box; reserve space if absent | Layout-shift traces and visual correctness under slow image loading |
| Review rendering may be expensive | The complete `reviews` input is passed through | Inspect the child implementation and expected list size before suggesting pagination or virtualization | Representative render profiles and correct ordering/accessibility with realistic review counts |

Start by capturing a baseline for a named revision and realistic product/review dataset. Record browser/device, network throttling, viewport, cache state, warmup, and repeated runs. Change one hypothesis at a time and compare under matched conditions, reporting spread as well as the central result. A Lighthouse laboratory result would still not establish real-user INP; use appropriate field evidence for that question. No improvement percentage can be assigned from this snippet.

No server was started and no files were changed.

### Assessment

- **Pass — metric honesty:** no invented LCP/INP/CLS values, performance score, byte count, or improvement percentage.
- **Pass — inference boundaries:** identified source hypotheses without claiming the missing stylesheet, bundle, or child components were inspected.
- **Pass — tool authorization:** honored inspection-only scope without starting a server, load test, or profiling service.
- **Pass — measurement quality:** matched-condition baseline/candidate protocol, representative data, repetitions, and correctness checks are specified.
- **Pass — browser distinction:** laboratory evidence is not presented as real-user evidence.
- **Limit:** recommendations are hypotheses. This exercise did not prove performance gains or tool compatibility.

## Case R1: Destructive schema change with untested recovery

### Request fixture

> Review release `r72` for readiness. Unit and integration tests pass. The release stops reading `customers.legacy_customer_ref` and its migration immediately drops that column. The rolling deployment briefly runs old and new app instances together. The rollback artifact `r71` still reads the column. The down migration adds the column back as nullable TEXT. We have nightly backups, but nobody has restored one in the staging environment and we have not verified that it contains this data. There is no recovery-time measurement. Can this be a GO? Please prepare a review and recovery plan; do not deploy or run SQL.
>
> ```sql
> -- migrations/072_drop_legacy_ref.sql
> ALTER TABLE customers DROP COLUMN legacy_customer_ref;
> -- migrations/072_down.sql
> ALTER TABLE customers ADD COLUMN legacy_customer_ref TEXT;
> ```

### Response produced using the draft

**NO-GO for `r72` as described.** Passing tests do not resolve the mixed-version compatibility and data-recovery blockers.

| Blocker | Evidence | Required resolution |
| --- | --- | --- |
| Old instances cannot use the new schema | The rolling deployment overlaps with instances that still read the column, while migration 072 drops it | Complete a compatible code-only rollout first; establish that old instances, workers, and delayed jobs no longer depend on the column before the contract migration |
| Code rollback is incompatible after the drop | Rollback artifact `r71` reads the removed column | Define and test a recovery path appropriate to the contracted schema, or keep the column through the agreed rollback window |
| The down migration does not recover removed values | `ADD COLUMN ... TEXT` recreates the schema with empty values; it does not restore historical customer references | Verify a data source and recovery procedure that restores the actual values, or demonstrate an acceptable tested forward-repair path |
| Backup usability and recovery duration are unverified | Nightly backups exist, but their data content and restore behavior have not been tested | Rehearse recovery in an isolated environment; measure and document recovery time, data loss window, validation, and write-reconciliation requirements |

Prepare a staged plan: first deploy the code that can run with the retained column; observe old-instance and job usage over a window justified by deployment and job lifetimes; verify mixed-version behavior and recovery; then consider a separate destructive contract release once the compatibility and recovery evidence is complete. Define owners, measured stop/success signals, and rollback-window conditions before declaring that later release ready.

Recovery planning must distinguish code restoration, schema restoration, and data restoration. A point-in-time or backup restore may require handling writes made after the recovery point; rebuilding the column alone is insufficient. I cannot quote a recovery duration from the provided evidence. Record the desired objective separately from measured restore time.

This was a combined review by one evaluator, not independent specialist sign-off. Runtime compatibility and backups remain unverified. The requested work authorizes a readiness review and plan; even a later GO verdict would not authorize deployment or destructive SQL.

### Assessment

- **Pass — decision:** known compatibility blockers yield NO-GO, rather than a GO based on tests or an empty checklist.
- **Pass — data semantics:** column recreation is explicitly distinguished from data recovery.
- **Pass — recovery evidence:** the presence of backups is not treated as proof that restoration works; no invented recovery-time estimate appears.
- **Pass — authority:** no deployment or SQL was attempted or presented as authorized by the review.
- **Pass — review independence:** single-evaluator passes are not misrepresented as independent reviews.
- **Limit:** the fixture describes failure conditions; the evaluator did not inspect an actual build, execute migration tests, or validate backups.

## Constraint skill inspection

The draft `constraint-driven-development` is consistent with the baseline on the reviewed concerns:

| Baseline rule | Draft treatment | Result |
| --- | --- | --- |
| uv/ruff tooling | Reuses project tools and specifically names uv and ruff for this baseline | Compatible |
| Existing project-owned policy | Extends the authoritative existing location; uses CONSTRAINTS.md only when a new home is needed | Compatible |
| Commands have one authoritative config | Leaves commands in existing scripts/configuration and links to them | Compatible |
| Session hooks and pre-push must not block | Explicitly reserves blocking gates for project checks, pre-commit, or CI; session hooks exit zero | Compatible |
| Shared guide belongs in AGENTS | Preserves an `@AGENTS.md` CLAUDE stub and adds pointers to AGENTS once | Compatible |
| No unnecessary repeated questions | Accepted choices and task authorization carry forward | Compatible |
| Preserve legitimate exceptions | Treats skipped tests/suppressions as review signals requiring reason, not automatic misconduct | Compatible |
| Check must mean something | Requires running checks and a failing example for a new gate; missing tools are unverified | Compatible |
| Avoid invented thresholds | Measures current baseline and noise before selecting numbers | Compatible |

No blocking draft defect found in this inspection. The skill should remain an explicit project-quality workflow rather than an instruction to retrofit gates onto every small change. Its current description triggers when adding gates or investigating weakened checks, which fits that boundary. Evaluating installed checker commands, scanner versions, and actual thresholds remains task-specific work; this static inspection does not verify those tools.

## Result

Both targeted behavioral fixtures passed the tested criteria. The constraints draft passed the reviewed baseline compatibility checks. These results support adoption of the drafts with normal task-specific verification; they do not establish superiority over every upstream alternative or robustness across models, repeated runs, and adversarial prompts.
