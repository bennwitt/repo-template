# Engineering skill selection — 2026-10-27

The selected workflow retains 35 Pocock skills and adds eight Addy-derived skills in focused
packs. Two Pocock skills are adapted locally to correct review scope and repository setup.
The monitoring specialist also receives narrow corrections discovered during comparison.
This is a best-fit engineering selection backed by source review and targeted behavioral
exercises, not a claim of universal superiority or a model benchmark.

## Evidence and method

- [Pocock: all 38 skills](evaluations/pocock.md), at
  [59db609eb1e18aaf59b63284d0e52255aff0c63c](https://github.com/mattpocock/skills/tree/59db609eb1e18aaf59b63284d0e52255aff0c63c).
- [Addy: all 25 skills, nine commands, four personas, references and hooks](evaluations/addy.md), at
  [aeac41d4d005999432bb7312f7ff06383a91d59d](https://github.com/addyosmani/agent-skills/tree/aeac41d4d005999432bb7312f7ff06383a91d59d).
- [Forward exercises and observed results](evaluations/behavior.md), performed independently
  of the draft author on local fixtures or supplied source scenarios.

Each source review considers workflow specificity, evidence/verification, distinct value over
the installed alternative, execution scope, cross-client portability, dependencies, context
cost and maintainability. Source bodies and executable/supporting material were inspected as
data; upstream scripts and runtime hooks were not executed. Static scans covered all 63 skills:
Pocock had no pattern findings; Addy's two injection-string hits were defensive examples.
Zero scanner findings do not prove safety. The comparison found defects beyond scanner coverage.

The detailed reports retain the evidence and recommendations from the review. The implemented
decisions below are authoritative for this revision. Other catalog sources were examined where
they overlapped; this was not an exhaustive audit of every third-party skill in the catalog.

## Implemented selection

| Capability | Selected route | Why this selection |
| --- | --- | --- |
| Requirements | Pocock grilling and to-spec | Existing interrogation, domain context and tracker integration |
| Planning | Pocock to-tickets | Acceptance criteria and dependencies without a competing plan-file convention |
| Implementation | Pocock implement / implement-spec | Existing TDD composition and explicit task-graph/worktree workflow |
| Testing/debugging | Pocock tdd / diagnosing-bugs | Public-interface tests, independent expectations and diagnostic loop |
| Review | Locally adapted Pocock code-review | Retains separate Standards/Spec passes; includes requested WIP and local requirements |
| Workflow setup | Locally adapted setup-matt-pocock-skills | Configures existing skills, preserves AGENTS authority, supports local tracking |
| Refactoring | Addy-derived code-simplification, dev-workflows | Behavior preservation, scoped incremental changes, explicit async/error/cleanup traps |
| Retirement | Addy-derived deprecation-and-migration, dev-workflows | Consumer inventory, phased schemas, concurrent backfills and honest recovery limits |
| Quality constraints | Addy-derived constraint-driven-development, delivery | Measured baselines, cost-aware checks and review of weakened tests/configuration |
| Implementation evidence | Addy-derived source-driven-development, delivery | Installed-version evidence and specific primary docs during implementation |
| Performance | Addy-derived performance-optimization, performance | Matched baselines, variability, profiles, attempt ledger and honest source-only audits |
| Instrumentation | Addy-derived observability-and-instrumentation, sre | Feature questions, correlation, bounded labels, sampling and verification |
| API contracts | Addy-derived api-and-interface-design, api | Atomic key claiming, request binding, crash windows, retry/expiry semantics |
| Release readiness | Addy-derived shipping-and-launch, delivery | Scoped independent checks, operational evidence, rollout/recovery and unknowns |

Existing specialist packs remain available. In `sre`, monitoring-expert keeps its infrastructure
references but is now a local adaptation: HTTP examples use configured route templates, error
ratios aggregate status consistently, and the tracing example imports its status enum. The
feature-instrumentation skill sets signal-design expectations; the specialist configures tools.
See the supporting [Prometheus vector-matching documentation](https://prometheus.io/docs/prometheus/latest/querying/operators/)
and [OpenTelemetry instrumentation API](https://opentelemetry.io/docs/languages/js/instrumentation/).

## What the nine Addy commands mean here

These are capability mappings, not installed aliases. Native skill invocation syntax depends on
the agent host; our catalog installs skill folders into both clients' established locations.

| Upstream entry point | Selected equivalent |
| --- | --- |
| /spec | to-spec, grilling |
| /plan | to-tickets |
| /build | implement or implement-spec |
| /test | tdd plus project checks |
| /review | adapted code-review and relevant specialist checks |
| /constraints | constraint-driven-development in delivery |
| /webperf | performance-optimization in performance, browser branch |
| /code-simplify | code-simplification in dev-workflows |
| /ship | shipping-and-launch in delivery; readiness only |

The four upstream personas contribute useful perspectives, but no persona plugin is installed.
Release readiness contains portable reviewer briefs; web performance contains the relevant
measurement-vs-static distinction. Hosts without subagents run sequential passes and disclose
that limitation. No competing universal router or automatic session-start activation is added.

## Deliberate exclusions and adaptations

Seventeen Addy skills remain excluded with individual reasons in the detailed matrix and
`.agents/skill-sources.json`. Overlap alone is not proof that an incumbent is better: the reviews
compare concrete mechanisms and costs. Addy's generic testing, planning and implementation
would impose a second process; selected capabilities fill specific gaps instead.

Important corrections include avoiding unconditional repeated approval gates, replacing
hardcoded rollout/budget guarantees, keeping secrets out of guard output, and distinguishing
schema recreation from data recovery. The upstream CI examples include raw shell interpolation
of workflow input and mutable action tags; the existing hardened baseline remains authoritative.
Upstream hooks that block sessions or rewrite source around reads are not installed.

Pocock's chief-of-staff, scaffold-exercises and setup-pre-commit remain excluded for broad
environment/task mandates, course-specific dependencies and conflicting hook ownership.
The 35 included skills retain their placements: 33 global and two in typescript. Six upstream
in-progress skills remain experimental and explicit-use; their status is listed in the
[project workflow guide](agents/workflow.md).

## Packaging and maintenance

The eight selected Addy skills are self-contained, locally maintained MIT adaptations. Their
names preserve discoverability while their content avoids unresolved external skill-folder
references. `derivedFrom` records the primary source path, reviewed commit and license;
`additionalPaths` records companion inputs used in a derivation. Original license text is
copied and generated notices identify the adaptations. Ordinary vendored skills remain
byte-identical except recorded frontmatter overrides.

`globals --upstream` compares derived source files/trees, additional paths and licenses against
the recorded revision. Changed inputs are manual-review items and adopted paths are not
rediscovered as new skills. `globals --upgrade` does not overwrite local adaptations. Excluded
skills are decisions to revisit when needs change, not a claim that their future revisions are
automatically audited. Use the pinned reports when reconsidering them.

## Validation and limits

The review fixture contained four defects across committed, staged, unstaged and untracked
files. The original review procedure enumerated one of the four files; the adapted procedure
enumerated all four and confirmed the defects with synthetic local inputs. The setup fixture
preserved existing AGENTS content and the exact CLAUDE import stub, wrote approved local
configuration without a remote, and produced identical hashes on a repeat run.

A source-only browser scenario produced hypotheses and a measurement plan without fabricated
metrics. A destructive column-drop scenario produced NO-GO and identified mixed-version and
data-restoration blockers. These are single-evaluator forward exercises, not blinded trials,
runtime performance measurements, or proof that every model will follow the skills.

Repository tests cover derived-source drift/discovery, template seed ownership, document links,
catalog provenance and adoption boundaries. Temporary repositories verify selected packs through
both client links, repeat-update idempotence and unchanged visible files for personal adoption.
No real machine globals, remote labels, deployment, commit or push is part of this change.
