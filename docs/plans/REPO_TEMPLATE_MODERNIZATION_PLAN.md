# Implementation Plan: Extend Existing Repo-Template Maintenance and Agent Capabilities

**Target:** `/ai/Moore/repo-template`  
**Execution environment:** Linux, with macOS compatibility  
**Agents:** Codex and Claude Code  
**Scope:** Existing packs, skills, MCPs, agent definitions, upstream sources, and maintenance workflows

## Mission

Modernize and expand the existing `repo-template` system by incorporating current Microsoft Foundry, LangChain, LangGraph, LangSmith, and MCP capabilities.

**This is an enhancement to an established, actively maintained repository. It is not a replacement architecture or a greenfield implementation.**

The repository already has machinery for managing, updating, and distributing packs, skills, MCP integrations, and agent configurations.

Discover that machinery, understand it, reuse it, and extend it.

The implementation must also broaden the current upstream admission policy, establish a maximum 24-hour freshness threshold, and incorporate LangChain's new beta Python MCP integration.

Complete the work rather than stopping at recommendations. Inspect, plan, implement, validate, and document.

---

## 1. Non-Negotiable Implementation Principles

### 1.1 Preserve existing maintenance workflows

Before editing code, investigate:

- Existing pack definitions and pack management.
- Skills registries, skill installation, and skill updating.
- MCP registries, configuration, and update workflows.
- Upstream repository tracking and synchronization.
- Existing automated maintenance agents.
- Scheduled maintenance tasks and CI workflows.
- Security scanners, compatibility checks, and admission guardrails.
- Repository initialization and upgrade commands.
- Agent instruction files and configuration propagation.
- Current testing, validation, and release workflows.

Identify the actual entry points and dependencies.

**Use the established update mechanisms for all new and existing capabilities.**

Do not introduce competing registries, independent update scripts, duplicate schedulers, or parallel skill installation systems.

If additional functionality is needed, extend the existing implementation through its established configuration, extension points, or smallest necessary code changes.

Preserve compatibility with previously generated repositories.

### 1.2 Inspect before modifying

Read the repository's `AGENTS.md`, `CLAUDE.md` if present, README, existing maintenance documentation, pack definitions, source manifests, and relevant tests.

Inspect Git status and existing user modifications.

Run the established validation suite and record the initial baseline.

Produce an internal Keep / Enhance / Add / Deprecate assessment.

Avoid assumptions about file locations, command names, or registry schemas.

### 1.3 Prefer augmentation over duplication

If a capability already exists:

1. Evaluate its implementation and upstream source.
2. Compare it against current official documentation.
3. Determine whether it should be retained, refreshed, or extended.
4. Update the existing asset where appropriate.
5. Preserve customizations and compatibility requirements.

Create a new asset only when no suitable existing capability can be extended.

The result should remain one coherent template-management system.

---

## 2. Expand the Existing Upstream Update Policy

### Objective

Every tracked upstream pack, skill, plugin, and MCP integration should be evaluated using a maximum **24-hour freshness threshold**.

Apply this policy to the entire existing upstream inventory, not only the integrations introduced by this project.

### 2.1 Refresh existing upstream sources

Use the repository's established update workflow to inventory and evaluate:

- All registered upstream repositories.
- Existing agent skill collections.
- Existing packs and pack dependencies.
- MCP server definitions and packages.
- Installed agent plugins and plugin marketplaces.
- Shared agent configuration templates.
- Existing tool adapters and integrations.
- Upstream dependencies referenced by managed capabilities.

Include sources that are currently disabled, pinned, or excluded, but preserve their intentional deployment or version restrictions.

### 2.2 Establish a 24-hour freshness policy

For each upstream source, use existing metadata or extend it to track:

- Source identity and canonical URL.
- Current installed or referenced version.
- Latest discovered upstream version or commit.
- Last successful upstream check, in UTC.
- Last successful synchronization.
- Last successful validation.
- Detected changes.
- Compatibility and security status.
- Whether an update is pending, blocked, or accepted.

Policy:

**If a source has not been successfully checked within the last 24 hours, the existing updater must evaluate it again.**

When newer content exists:

1. Retrieve upstream changes through the existing updater.
2. Generate the normal change comparison.
3. Evaluate compatibility and security.
4. Incorporate changes permitted by the repository's update policy.
5. Execute the existing validation gates.
6. Record the result and source revision.

Do not update a successful-check timestamp if the check failed.

If the existing maintenance cadence does not guarantee a check within 24 hours, adjust its established scheduling mechanism. Do not add another scheduler.

Maintain separate timestamps for checking, synchronizing, and validating.

An upstream check with no changes should not rewrite files unnecessarily.

### 2.3 Widen the existing admission guardrail

The current guardrail should become more receptive to new and updated upstream capabilities.

**Replace unnecessarily restrictive allowlisting with risk-based admission and validation, using the existing policy implementation.**

Suggested admission model:

| Classification | Behavior |
|---|---|
| Established official upstream | Automatically discover, evaluate, and incorporate compatible low-risk updates |
| Established community upstream | Automatically discover and evaluate; incorporate after existing risk and compatibility checks |
| New upstream source | Register as a candidate, inspect provenance and content, then admit according to risk |
| Preview or beta capability | Allow inclusion with explicit stability metadata, isolated dependencies, and appropriate tests |
| Capability requiring elevated permissions | Require review before granting access or enabling privileged operations |
| Malicious, unverifiable, or unsafe content | Reject or quarantine with recorded findings |

Do not reject useful new skills merely because they have not previously appeared in the registry.

Do not automatically trust executable content because it comes from a well-known organization.

Retain protections for:

- Prompt injection and malicious skill instructions.
- Executable installation hooks.
- Unexpected filesystem or network operations.
- Secret and credential exposure.
- Dependency vulnerabilities.
- Privilege escalation.
- Destructive operations.
- Unreviewed production infrastructure changes.

Reuse existing security skills and scanners, including `agent-skill-scanner` where present.

The intended behavior is **broader discovery and easier admission, with proportionate security controls**.

### 2.4 Preserve update traceability

Every accepted update must retain enough information to identify:

- What changed.
- Which upstream version introduced the change.
- Which local assets were affected.
- Which checks passed or failed.
- Whether an update requires operator intervention.
- How to revert or pin the previous version.

Use existing reports and manifests wherever possible.

---

## 3. Add and Maintain Official LangChain Ecosystem Sources

Integrate the following sources into the existing upstream registry or corresponding source-tracking mechanism.

| Source | Purpose |
|---|---|
| `https://github.com/langchain-ai/langchain-plugins` | Official Codex/Claude plugin marketplace |
| `https://github.com/langchain-ai/langchain-skills` | LangChain, LangGraph, Deep Agents skills |
| `https://github.com/langchain-ai/langsmith-skills` | Observability, tracing, datasets, evaluations |
| `https://github.com/langchain-ai/langchain` | Framework releases and native MCP API changes |
| `https://docs.langchain.com/` | Current implementation guidance and compatibility information |

Update existing source registrations instead of creating duplicates.

### 3.1 LangChain capabilities

Evaluate and integrate skills covering:

- Agent construction and lifecycle.
- Tool calling and structured output.
- Middleware and execution controls.
- RAG and retrieval.
- Streaming and asynchronous execution.
- Dependency management.
- Model-provider integrations.
- Testing and evaluation.

### 3.2 LangGraph capabilities

Evaluate and integrate skills covering:

- StateGraph architecture.
- Nodes, edges, reducers, and routing.
- Persistent state and checkpointing.
- Durable execution.
- Human-in-the-loop interrupts and resumption.
- Multi-agent orchestration.
- Error recovery.
- LangGraph CLI and deployment.
- LangSmith integration.

### 3.3 Deep Agents

Make official Deep Agents skills discoverable as an optional capability within the existing pack structure.

Do not automatically add Deep Agents to every LangGraph application.

Prefer the simplest suitable orchestration architecture.

### 3.4 LangSmith

Integrate official skills for:

- Tracing and observability.
- Dataset construction.
- Evaluator design.
- Regression testing.
- Experiment comparison.
- Agent quality measurements.

Support the official `langsmith-mcp` plugin where appropriate.

Keep authenticated LangSmith access optional and separate from ordinary development tooling.

---

## 4. Integrate Native LangChain MCP Beta

### Objective

Add support for LangChain's native Python MCP integration while preserving compatibility with existing MCP adapters.

This capability is particularly important for LangGraph applications developed for Azure Container Apps, local Docker execution, or Foundry Hosted Agents.

### 4.1 Current integration

Official documentation:

`https://docs.langchain.com/oss/python/langchain/mcp`

The native Python MCP implementation is available through:

`langchain[mcp]>=1.4.0`

Import:

`from langchain.mcp import MCPAdapter`

The API is currently beta and must be identified as such in the existing capability metadata.

### 4.2 Integrate with existing packs

Determine which existing pack owns Python agent runtime integrations.

Extend that pack to support:

- Native LangChain MCP clients.
- Asynchronous MCP tool discovery.
- Multiple MCP server connections.
- Streamable HTTP connections.
- Local stdio servers.
- In-process MCP testing.
- Tool metadata and structured results.
- Authentication and authorization.
- Timeouts and error handling.
- Tool approval policies.
- LangGraph orchestration integration.

Avoid creating a duplicate MCP pack if the repository already has one.

### 4.3 Reference implementation

Create or extend the existing MCP reference fixture using the following basic integration pattern:

```python
from langchain.agents import create_agent
from langchain.mcp import MCPAdapter


async def run_agent(model, server_url: str, message: str):
    async with MCPAdapter(server_url) as adapter:
        tools = await adapter.list_tools()

        agent = create_agent(
            model=model,
            tools=tools,
        )

        return await agent.ainvoke({"messages": [{"role": "user", "content": message}]})
```

The implementation must be modular and testable.

This example illustrates the supported API pattern; adapt it to the repository's current dependency and application conventions.

### 4.4 Compatibility with existing adapters

Search for existing use of:

`langchain-mcp-adapters`

Determine whether it is used by any existing templates, examples, or generated assets.

Do not blindly replace working implementations.

Provide a compatibility strategy:

- Preserve existing adapter behavior.
- Add the native beta implementation as a selectable capability.
- Prefer the native implementation for new opt-in Python MCP examples when compatible.
- Verify differences in connection handling, tool discovery, metadata, and invocation behavior.
- Provide migration guidance for existing consumers.
- Track upstream beta API changes through the established updater.

Where useful, introduce a small internal interface allowing the selected MCP backend to change without rewriting the consuming LangGraph application.

Avoid overengineering this abstraction.

### 4.5 Beta quality gates

Add tests for:

- MCP tool discovery.
- Tool invocation.
- Async connection lifecycle.
- HTTP transport.
- Local/in-process server execution.
- Multiple server integration.
- Authentication failures.
- Tool exceptions and timeouts.
- Structured responses.
- Tool name collisions.
- Unauthorized write operations.
- Compatibility with supported LangChain and LangGraph versions.

Use a local test MCP server so the baseline suite can run without network credentials.

Ensure the beta dependency remains isolated and explicitly versioned in its consuming environment.

Do not impose beta dependencies globally across unrelated template packs.

---

## 5. Extend Microsoft Azure and Foundry Capabilities

Evaluate the following official sources:

- `https://github.com/microsoft/azure-skills`
- `https://github.com/microsoft/skills`
- `https://learn.microsoft.com/`

Integrate them using the same existing upstream update mechanism and 24-hour policy.

### Required capabilities

**Azure development**

- Azure resource discovery.
- Authentication and managed identities.
- Azure Developer CLI.
- Container Apps and container deployment.
- Infrastructure validation.
- Observability and diagnostics.
- Cost and resource configuration.

**Microsoft Foundry**

- Foundry project and model configuration.
- Foundry agent development.
- Hosted Agents deployment.
- LangGraph hosting through the appropriate Foundry adapter.
- Container packaging.
- Foundry MCP integration.
- Toolboxes and runtime tool access.
- Agent evaluations.
- Governance and identity.

Use official Microsoft skills and plugins where suitable.

Avoid duplicating skills already supplied through the Azure Skills plugin.

### Deployment guidance

Maintain a framework-independent LangGraph application that can be deployed through:

1. A Foundry Hosted Agent adapter.
2. A FastAPI/Container Apps adapter.
3. Local Python or Docker execution.

Preserve the same domain logic and graph implementation across the deployment targets.

Keep this example optional within the existing template structure.

No live Azure deployment or resource modification is authorized as part of this maintenance task.

---

## 6. Support Both Codex and Claude Code

### Objective

Ensure that packs, skills, MCP definitions, and maintenance improvements can be consumed by both agent environments.

### 6.1 Shared capability model

Do not maintain independent copies of the same skill solely for Codex and Claude.

Use the repository's established shared asset definitions and generate or install host-specific configurations when necessary.

Support:

| Capability | Codex | Claude Code |
|---|---|---|
| Repository instructions | `AGENTS.md` | `CLAUDE.md` |
| Agent skills | Supported | Supported |
| MCP servers | Supported | Supported |
| Plugin marketplaces | Supported | Supported |
| Existing pack installation | Preserve | Preserve or extend |
| Existing pack updates | Preserve | Preserve or extend |
| Upstream freshness tracking | Shared | Shared |
| Validation and security | Shared | Shared |

Honor the current repository's configuration layout rather than forcing these exact files or directories into every generated project.

### 6.2 LangChain official plugin marketplace

Source:

`https://github.com/langchain-ai/langchain-plugins`

Integrate the following plugin capabilities through the existing pack and plugin management mechanisms:

- `langchain-skills`
- `langchain-mcp`
- `langsmith-skills`
- `langsmith-mcp`

For Codex, current official marketplace commands include:

```bash
codex plugin marketplace add \
  langchain-ai/langchain-plugins

codex plugin add \
  langchain-skills@langchain-plugins

codex plugin add \
  langchain-mcp@langchain-plugins
```

For Claude Code, the corresponding commands are:

```text
/plugin marketplace add langchain-ai/langchain-plugins
/plugin install langchain-skills@langchain-plugins
/plugin install langchain-mcp@langchain-plugins
```

These are reference installation commands.

The repository's existing tooling remains responsible for determining which capabilities are already installed and how to update them.

Do not globally execute these commands unless authorized.

### 6.3 Microsoft plugin support

Support official Azure Skills integration for both Codex and Claude Code.

Account for host-specific plugin installation and update behavior.

The source of capability definitions should remain shared wherever possible.

### 6.4 MCP configuration propagation

Ensure the existing template can configure or provide installation instructions for:

- LangChain Docs MCP.
- LangChain API Reference MCP.
- Microsoft Learn MCP.
- Azure MCP.
- Foundry MCP.
- Optional LangSmith MCP.

Preserve existing GitHub, Playwright, internal, and custom MCP configurations.

Use deduplication rather than registering the same server through both a plugin and a standalone MCP definition.

Maintain a strict distinction between developer MCPs and MCP connections used by deployed applications.

---

## 7. Augment Existing Packs and Agent Instructions

After the upstream inventory and compatibility review, determine which packs should receive the new capabilities.

Do not assume new pack names are needed.

Suggested logical capability mapping:

| Existing pack category | Enhancements |
|---|---|
| Core agent development | LangChain fundamentals and updated skill discovery |
| Agent orchestration | LangGraph workflows, state, persistence, HITL |
| MCP development | Native LangChain MCP beta, client/server testing |
| Azure development | Microsoft Azure Skills and MCP |
| AI platform deployment | Foundry Hosted Agents |
| Observability and testing | LangSmith and existing evaluation tooling |
| Coding-agent environment | Codex and Claude plugin compatibility |

Update the existing agents and instructions to recognize these capabilities.

Agents should:

- Discover installed capabilities before adding new ones.
- Use official upstream documentation for changing APIs.
- Invoke established repo-template maintenance workflows.
- Respect the 24-hour upstream freshness policy.
- Select appropriate packs for new projects.
- Prefer established local tooling.
- Preserve repository-specific modifications.
- Validate changes before propagation.
- Keep deployment operations separate from development tooling.
- Update `HANDOFF.md` after meaningful work.

Avoid loading large collections of skills into every agent context by default.

Use the existing skill discovery and progressive-loading behavior.

---

## 8. Integrate With the Existing Maintenance Lifecycle

This is the central requirement.

**Do not create a new maintenance system. Extend the existing one.**

Inspect how the repository currently performs:

1. Source discovery.
2. Upstream version checks.
3. Pack and skill updates.
4. MCP definition updates.
5. Security evaluation.
6. Merge and conflict handling.
7. Testing.
8. Registry or manifest updates.
9. Distribution to existing repositories.
10. Maintenance reporting.

For each step, identify the required enhancements.

Expected behavior after implementation:

**Normal maintenance**

The existing update workflow checks applicable upstream sources, identifies changes, evaluates compatibility, and applies permitted updates using current repository conventions.

**24-hour freshness**

Sources that have not been checked successfully within 24 hours are re-evaluated. Updated content follows the same existing validation and update path.

**New source discovery**

New capabilities from recognized upstreams are evaluated under the expanded admission policy and incorporated when permitted.

**Pack updates**

Existing packs gain new or updated skills, MCPs, and plugin support without overwriting local modifications.

**Repository upgrades**

Projects already created from `repo-template` can receive appropriate capability updates through the established upgrade process.

**Dry-run and review**

Existing preview, diff, and conflict-resolution behavior must continue to work.

**Failure recovery**

Failed updates preserve the previous usable state and produce actionable diagnostics.

Where the existing maintenance code lacks one of these capabilities, implement the smallest extension compatible with its current architecture.

---

## 9. Validation Requirements

Run the repository's established validation suite and augment its coverage.

Required scenarios:

- Existing maintenance workflows continue to work.
- Existing pack manifests remain compatible.
- Existing skill updates remain functional.
- Existing MCP definitions are retained.
- New upstream sources are discovered.
- Sources older than 24 hours are rechecked.
- Fresh sources are not unnecessarily refreshed.
- Failed checks do not incorrectly update freshness timestamps.
- Upstream changes are detected and incorporated according to policy.
- Duplicate skills and MCP registrations are prevented.
- Broadened admission rules still reject unsafe assets.
- Codex configurations validate.
- Claude Code configurations validate.
- LangChain and LangGraph skills are discoverable.
- Native LangChain MCP beta tests pass.
- Legacy MCP adapter examples remain functional.
- Foundry development capabilities are available through the appropriate packs.
- Optional authenticated integrations fail gracefully when credentials are unavailable.
- Repeated updates are idempotent.
- Existing generated repositories remain compatible.
- Existing security, packaging, and repository standards remain intact.

Use the current test harness and CI system.

Introduce additional test fixtures only where necessary.

Do not silently skip failing validations.

---

## 10. Execution Sequence

Execute the following phases in order.

### Phase 1 — Baseline

- Inspect the repository.
- Identify existing update commands and workflows.
- Inventory all packs, skills, MCPs, plugins, and upstream sources.
- Review existing security and admission policies.
- Run baseline tests.
- Record findings.

### Phase 2 — Update policy enhancement

- Implement the 24-hour source freshness policy through existing machinery.
- Broaden the existing upstream admission guardrail.
- Preserve security and compatibility checks.
- Add or extend tests.
- Validate normal maintenance behavior.

### Phase 3 — Full upstream refresh

- Run the established updater against all eligible existing sources.
- Evaluate outdated skills, packs, and MCP definitions.
- Incorporate compatible updates according to policy.
- Preserve local changes.
- Record updates and exceptions.

### Phase 4 — New capability integration

- Add official LangChain ecosystem sources.
- Add or refresh Microsoft Foundry sources.
- Incorporate LangGraph and LangSmith skills.
- Integrate native LangChain MCP beta.
- Extend Codex and Claude support.
- Resolve duplicates and source ownership.

### Phase 5 — Reference implementations

- Update or add an optional LangGraph agent example.
- Demonstrate native MCP tool consumption.
- Provide Foundry and Container Apps hosting guidance.
- Validate the reference implementation.

### Phase 6 — Regression and maintenance validation

- Run existing tests and new integration tests.
- Verify idempotency.
- Verify 24-hour freshness behavior.
- Verify security guardrails.
- Verify Codex and Claude compatibility.
- Verify changes remain compatible with existing repo initialization and upgrades.

### Phase 7 — Documentation and handoff

Update existing documentation and `HANDOFF.md`.

Report:

- Existing workflows discovered and reused.
- Upstream sources evaluated.
- Existing assets refreshed.
- Newly incorporated capabilities.
- Admission-policy changes.
- Freshness-policy changes.
- Native LangChain MCP beta implementation.
- Codex and Claude integration changes.
- Tests executed and results.
- Outstanding incompatibilities.
- Any deferred or blocked changes.

---

## 11. Definition of Done

The task is complete when:

- [ ] Existing maintenance workflows remain the sole mechanism for updating managed capabilities.
- [ ] All existing upstream sources have been evaluated.
- [ ] A maximum 24-hour source-check freshness policy is implemented.
- [ ] Existing stale packs, skills, and MCP integrations have been refreshed where compatible.
- [ ] The upstream admission guardrail is more permissive while retaining risk-based security checks.
- [ ] Official LangChain and LangGraph capabilities are incorporated.
- [ ] Native `langchain[mcp]` beta is supported and tested.
- [ ] Existing legacy MCP consumers are preserved or safely migrated.
- [ ] Microsoft Azure and Foundry capabilities are current.
- [ ] Codex and Claude Code are both supported.
- [ ] Duplicate capabilities and parallel update mechanisms have been avoided.
- [ ] Existing pack installation and repository upgrade functionality remains compatible.
- [ ] Existing and new tests pass, with exceptions explicitly documented.
- [ ] Documentation and `HANDOFF.md` are updated.

## 12. Final Agent Directive

Work directly in the existing cloned `repo-template` repository.

**Do not redesign or replace the repository's existing pack, skill, MCP, or upstream update system.**

Your first responsibility is to discover and understand the current implementation.

Your second responsibility is to modernize existing upstream content and enhance the established maintenance pipeline.

Your third responsibility is to integrate LangChain, LangGraph, LangSmith, Microsoft Foundry, and native LangChain MCP beta capabilities for both Codex and Claude Code.

Make the current maintenance infrastructure more capable, more current, more extensible, and less restrictive about admitting useful upstream changes.

Preserve security controls, user-authored conventions, and reproducibility.

Do not introduce unnecessary competing frameworks or workflow mechanisms.

Proceed through inspection, implementation, testing, and documentation. Do not stop after producing an analysis or another plan.

If a specific implementation detail differs from this plan, favor the repository's established conventions and document the reason.

Only stop for a consequential destructive operation, an unresolved security issue, or an authorization requirement that cannot safely be satisfied.

**Expected outcome: The existing repo-template continues to operate exactly as intended, but now maintains a broader, fresher, Codex-and-Claude-compatible ecosystem of agent development capabilities, including LangChain's native MCP beta.**
## Implementation record

Implemented in the existing CLI, registries, updater transactions and catalog workflow. The
approved defaults are 24-hour successful-check freshness, a one-day executable-release cooldown,
offline use with a visible warning, and App-mediated automatic PR merging after required checks.
Native providers remain optional; writes need explicit machine-local activation. Review-required
upstream candidates remain deferred. See `HANDOFF.md` for accepted revisions, tests, activation
requirements and rollback, and `docs/maintenance.md` for the implemented operator workflow.
