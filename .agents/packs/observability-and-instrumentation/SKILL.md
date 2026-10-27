---
name: observability-and-instrumentation
description: Instrument a feature so its behavior and failures can be diagnosed. Use for structured logs, request/job correlation, bounded metrics, traces, symptom alerts and verification of telemetry.
---

# Feature observability

Read the existing logging, metrics and tracing stack before adding instrumentation. Use the
installed SDK and existing transport. The `monitoring-expert` and `sre-engineer` skills cover
broader monitoring architecture and SLO/incident work; this workflow focuses on one feature.

1. Name the operational questions: did the operation succeed, how long did it take, where did
   it fail, who owns it, and how can a retry or background job be followed?
2. Map entry points, dependency calls, queue boundaries and completion/failure paths. Define
   what constitutes one logical operation so retries and duplicate deliveries do not inflate
   success counts or hide failure rates.
3. Instrument the smallest useful signals, using the existing project's conventions.
4. Verify the telemetry with representative successful, failing, retrying and asynchronous
   executions. State whether evidence comes from local capture or a deployed backend.

## Signal design

| Signal | Contract |
| --- | --- |
| Logs | Structured event/operation, outcome, duration and correlation; stable names |
| Metrics | Rates, errors and duration for requests; utilization/saturation for resources |
| Traces | Propagate context through service calls and jobs; span ownership and useful status |
| Alerts | User-visible symptom, window/threshold, owner and actionable runbook |

Use bounded label sets such as route templates and error classes. User IDs, request IDs, raw
URLs, query strings and exception text belong neither in metric labels nor in unbounded dimensions.
Never log credentials or full sensitive payloads. Minimize/redact personal data and inspect
exported events, not only logging call sites. Preserve useful correlation without disclosing it
across tenants or trust boundaries.

Validate and bound inbound correlation IDs or generate local IDs. Propagate correlation plus
an originating entry-point identifier across jobs; keep entry-point names a controlled vocabulary.
Define telemetry retention, access controls and cost budgets. Tail sampling cannot recover a
trace already discarded by head sampling.

Check instrumentation cost, sampling, cardinality and exporter failure behavior. Telemetry failure
should follow the application's stated reliability policy; don't silently add a synchronous
network dependency to a critical path. Record where sampling can hide rare events.

For each alert, connect the symptom to a diagnostic query/dashboard and a runbook containing
first checks, mitigation and escalation. Test the condition in a local fixture or preview where
possible. Creating an alert rule is distinct from proving that notification delivery works.

Finish with the signals added, example redacted events, metric labels, a trace/correlation path,
verification evidence, and backend checks that remain unavailable. Use existing services;
provisioning a telemetry account or sending production data requires task-specific authorization.

Adapted from Addy Osmani's observability skill and checklist (MIT); reviewed inputs are pinned
in the standards catalog.
