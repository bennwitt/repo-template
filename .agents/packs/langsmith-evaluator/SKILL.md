---
name: langsmith-evaluator
description: "Build offline and online LangSmith evaluators. Use when the user requests this LangSmith workflow."
license: MIT
---

# langsmith-evaluator

Inspect real agent outputs before writing extraction logic. Use deterministic evaluators for objective contracts and calibrated model judges for subjective quality. Distinguish local evaluate() results from uploaded run rules. Test positive and negative fixtures before publishing an evaluator.

1. Inspect installed capabilities, project dependencies and the current official LangSmith
   documentation. Reuse the project's dependency manager and locked SDK; SDK and CLI credentials
   are separate. If the CLI is absent, prefer the SDK already declared by the project.
2. Confirm the intended endpoint, workspace and project through read-only inspection. Authentication
   belongs to the machine's environment or the client's OAuth connection. Keep API keys out of
   arguments and logs; do not read secret files to discover credentials.
3. Preview consequential changes against that target. Execute only the user's authorized scope;
   verify the resulting objects by their stable identities. Missing credentials leave authenticated
   work pending; local fixture-based evaluation remains available.
4. Record inputs, dataset/evaluator versions, outcomes and limits. Product feedback is sent only
   when the user explicitly requests it. Installation scripts must be downloaded and inspected,
   version-pinned and separately authorized before execution.

This is a local MIT adaptation of [LangChain's official guidance](https://github.com/langchain-ai/langsmith-skills/tree/13c168b28dbc3a7679e8f0358160063ad3329694/config/skills/langsmith-evaluator). It preserves the
workflow while removing command-line secrets, implicit feedback submission and uninspected
remote installation. Use the upstream references for API detail, subject to these boundaries.
