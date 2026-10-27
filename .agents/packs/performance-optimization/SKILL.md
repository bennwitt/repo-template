---
name: performance-optimization
description: Diagnose and improve measured application performance. Use for latency or throughput regressions, expensive queries, memory growth, browser responsiveness, or load-time and bundle budgets.
---

# Measured performance

Define the user's performance problem and scope before optimizing. Read existing SLOs and
budgets; when absent, agree a workload and success criterion based on observed needs. Distinguish
latency percentiles, throughput, memory, startup time and browser user experience.

## Measurement protocol

Record version/revision, dataset, machine/runtime, concurrency, cache state, warmup, duration
and repetitions. Compare baseline and candidate under matched conditions, with correctness
checks unchanged. State variability and tradeoffs; one faster run does not establish a win.
Profile first, identify the dominant cost, change one hypothesis, and measure again.

Keep a short attempt ledger:

| Hypothesis and change | Baseline | Candidate | Variability/tradeoff | Keep or revert |
| --- | --- | --- | --- | --- |

Stop when the agreed target is met, evidence disproves the hypothesis, or further work needs
a new scope decision. Undo only your own unsuccessful edits. Preserve measurements that explain
why an apparently attractive optimization was rejected.

## Choose the relevant branch

**Service or database:** inspect request traces, query counts and execution plans under the
representative load. Separate CPU, I/O, lock and queue wait. Check N+1 access, unbounded reads,
pool exhaustion and allocation pressure before adding caches. Treat `EXPLAIN ANALYZE` as query
execution: use a safe fixture/read-only workload or existing authorization, especially for writes.
Verify an index improves the actual plan and account for its write/storage cost.

For caching, include tenant, permissions and all result-changing inputs in the key; define
invalidation, freshness and concurrent-miss behavior. Test isolation, stale values and stampedes.
Increasing a pool can shift overload to the database; size against the total instance count.

**Browser:** distinguish a source-only inspection from a measured runtime audit. Inspect bundle
and network waterfalls, long tasks, layout shifts, image loading and actual render profiles.
Use supplied Lighthouse/trace/field artifacts or available browser tooling; record URL, device,
throttling, cache and measurement conditions. A lab report is not field evidence, and a source
heuristic cannot produce a measured score or prove real-user INP. Report unavailable metrics.
Use project Core Web Vitals budgets and verify current metric definitions when needed.

**Memory or batch work:** measure peak/steady-state memory, allocations, retained objects,
throughput and input scaling. A microbenchmark must represent the production operation before
it can justify a system-level claim.

## Completion

Report the bottleneck evidence, matched measurements, correctness checks, cost and remaining
uncertainty. Keep only supported improvements. Add a stable regression check when the benchmark
can distinguish real regressions from noise; otherwise preserve a reproducible measurement recipe.
No live load test or new external profiling service is implied by a request to inspect code.

Adapted from Addy Osmani's performance skill, checklist and web-performance-auditor (MIT).
All reviewed input paths are pinned in the standards catalog; no persona installation is needed.
