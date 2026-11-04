# Trace causes and wait for observable conditions

Read this when a failure appears far from its originating input, or a reproduction depends on
asynchronous state. Keep the main diagnosis loop: symptom-specific reproduction, falsifiable
hypotheses, focused instrumentation and cleanup.

## Trace backward across boundaries

Start at the observed failure and follow the value/state through callers, adapters and storage
until you find the first violated contract. At each boundary record expected versus observed
values and where the expectation comes from. Use redacted, minimal probes to distinguish
hypotheses; avoid broad logs of tokens, payloads or environment variables. Fix the cause at the
appropriate boundary, then verify the original caller's scenario and affected contracts.

Validate at boundaries that establish trust or invariants. Duplicating validation at every
layer is not inherently safer. For filesystem containment use resolved, component-aware paths
and the relevant platform's symlink/race protections; a string-prefix match is not containment.

## Wait for a condition, with bounds

Prefer the test framework's assertion retry, event notification or existing wait helper. Wait
for the specific state needed by the next action, reading fresh observations each attempt.
Set a deadline and useful failure diagnostics; add cancellation and clean up timers/listeners
on success, error and timeout. Use a monotonic clock for elapsed deadlines when available.
Choose the polling interval for the workload instead of imposing a universal 10 ms loop.

Separate readiness from the behavior under test. For cancellation, establish that work really
started before cancelling, then assert cleanup. For debounce/throttle tests, controlled time
is part of the behavior; an intentional time advance is appropriate. Test timeout/error paths
so a wait cannot hang forever or leave background work after the test ends.

Adapted from obra/superpowers root-cause tracing and condition-based waiting references (MIT),
with bounded cleanup, redaction and path-containment corrections. Provenance is in the catalog.
