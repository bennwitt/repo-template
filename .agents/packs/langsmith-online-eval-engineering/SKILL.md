---
name: langsmith-online-eval-engineering
description: "Design production LangSmith evaluation and monitoring. Use when the user requests this LangSmith workflow."
license: MIT
---

# langsmith-online-eval-engineering

Define the failure being detected, sampling policy, cost budget and actionable threshold. Online evaluators receive a run without a reference example. Validate against historical traces before enabling a rule. Plan alert ownership, false-positive review and rollback.

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

This is a local MIT adaptation of [LangChain's official guidance](https://github.com/langchain-ai/langsmith-skills/tree/13c168b28dbc3a7679e8f0358160063ad3329694/config/skills/langsmith-online-eval-engineering). It preserves the
workflow while removing command-line secrets, implicit feedback submission and uninspected
remote installation. Use the upstream references for API detail, subject to these boundaries.
