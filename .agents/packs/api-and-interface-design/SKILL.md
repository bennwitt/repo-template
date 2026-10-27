---
name: api-and-interface-design
description: Design compatible API contracts, especially retry and idempotency behavior. Use for public interface changes, state-changing endpoints, queue consumers, error semantics and concurrent duplicate requests.
---

# API contracts and retries

Read consumers and existing conventions before designing an interface. Use `api-designer` for
REST/OpenAPI details, `graphql-architect` for GraphQL, and `codebase-design` for module depth;
this workflow adds observable compatibility and retry semantics.

Define inputs, outputs, authorization, errors, ordering, side effects, timeouts and supported
versions. Document missing/null/empty distinctions and partial-update semantics. Validate external
data at trust boundaries; enforce internal invariants wherever ownership or concurrency requires
them. Static types alone do not validate runtime input.

Preserve observable behavior consumers rely on. Additive fields can still break strict clients,
serialized snapshots or exhaustive matching: test representative consumers rather than declaring
all additions compatible. Choose pagination and stable ordering for unbounded collections.
Fit the project's naming/versioning policy rather than mandating a REST style for every interface.

## Idempotency lifecycle

For a state-changing operation or at-least-once message consumer, specify whether retrying is safe.
If it is, design the stored state, not just an `Idempotency-Key` header:

1. Define a stable logical-operation key and scope it to the principal/tenant and operation.
   It must survive retries. A UUID generated once per operation is valid; a fresh UUID per
   attempt is not. Authenticate/authorize every attempt, including response replay.
2. Bind the key to a canonical request fingerprint; a different payload with the same key
   receives a defined conflict, not the earlier response.
3. Claim it atomically using a unique constraint, conditional write or equivalent mechanism.
   A separate lookup followed by insert is racy.
4. Define in-flight duplicate behavior: bounded wait, accepted status with polling, or conflict.
   Store the completed outcome for deterministic replay and decide which failures are retryable.
5. Make the key record and local side effect transactional where possible. For an external
   effect, use the provider's idempotency contract, an outbox/inbox, or reconciliation. A stored
   key alone cannot close the crash window between an external effect and recording success.
6. Set retention against the longest retry/replay path, including delayed jobs and dead letters.
   Define behavior after expiry and how ambiguous in-flight records recover after a crash.

Prove these cases with integration tests at the persistence boundary: concurrent duplicates,
same key/different body, cross-tenant reuse, crash before and after side effects, timeout/retry,
failed operation, and expiry/replay. State any external-effect window the design cannot close.

Deliver the contract, state transitions, compatibility decision and evidence. Avoid promising
exactly-once effects when the participating systems cannot enforce that guarantee.

Adapted from Addy Osmani's `api-and-interface-design` (MIT); pinned provenance is in the
standards catalog.
