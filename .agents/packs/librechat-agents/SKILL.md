---
name: librechat-agents
license: MIT
description: "@librechat/agents, LibreChat's LangGraph agent runtime (Run, sessions, HITL, registerProvider, handoffs, SkillTool, ToolSearch), and tool registries for LLM agents: deferred tools, the MCP Registry API, LibreChat tool and skill registration. Use when building on the SDK or designing a tool registry."
---

# @librechat/agents and tool registries

`@librechat/agents` (npm, MIT, repo `LibreChat-AI/agents`) is the TypeScript runtime LibreChat
runs its agents on: LangGraph graphs, provider adapters, streaming handlers, tool execution,
tool search, skills, subagents and sessions. It releases almost daily (4.2.4 through 4.2.10 landed
between 2026-11-15 and 2026-11-18), so this skill was checked on 2026-11-18 against `main` at
`20b1fad` (package version 4.2.10), LibreChat `main` at `d4e85d2` (release v0.8.9, 2026-11-17)
and `modelcontextprotocol/registry` `main` at `115f852`. Section 1 tells you how to re-check.
The sibling `librechat` and `librechat-docs` skills in this pack cover installing and configuring
LibreChat itself; this skill covers the SDK and the registry patterns around it.

## 1. Look it up for the version you run

- **Pin the newest release at least 7 days old.** As of 2026-11-18 that is **`4.2.2`**
  (published 2026-11-10; 4.2.3 and later are younger than a week). Re-check with
  `npm view @librechat/agents time --json | tail -15`, and read that version's peers with
  `npm view @librechat/agents@4.2.2 dependencies engines`. 4.2.10 declares `node >=24.0.0` and
  pins `@langchain/core` and `@langchain/langgraph` exactly; install the same versions it pins.
- **Read the source at your tag**, not the docs site:
  `gh api 'repos/LibreChat-AI/agents/contents/README.md?ref=v4.2.2' -H 'Accept: application/vnd.github.raw'`.
  Start with `README.md`, then `CONTEXT.md` (domain terms), `docs/multi-agent-patterns.md`,
  `docs/subagent-context.md`, `docs/tool-approval-replay.md`, `docs/adr/*.md`, and the types in
  `src/types/run.ts`, `src/types/graph.ts`, `src/types/hitl.ts`, `src/session/types.ts`.
- **LibreChat's host-side docs** live in `LibreChat-AI/LibreChat`: `docs/sdk/agents.md`
  (SDK runtimes), `docs/skills-management-api.md`, `skill/README.md`, `docs/tool-approval-modes.md`,
  `docs/mcp-apps.md`, and the commented `librechat.example.yaml`.
- Exact API shapes quoted from those files are in [references/sdk-api.md](references/sdk-api.md)
  and [references/tool-registries.md](references/tool-registries.md).

## 2. Choose the entry point

| You want | Use |
| --- | --- |
| A script, CI job or service that chats with an agent and can resume later | `createAgentSession` (section 3): JSONL journal, checkpoints, `fork`/`clone`/`compact` |
| Your own host app that streams events to a UI | `Run.create` + `processStream` with `customHandlers` |
| A custom agent inside a LibreChat deployment | A LibreChat SDK runtime (`endpoints.agents.sdkRuntimes`), which hands you a `Run` config |
| A chat model this package doesn't ship | `registerProvider` before the first run |
| Dozens of tools or MCP servers without paying for every schema each turn | `defer_loading: true` + `tool_search` (section 4) |
| Reusable instructions the model loads on demand | Skills: a budgeted catalog in the system prompt + the `skill` tool |
| Several agents handing work to each other | `type: 'multi-agent'` with `edges` (section 5) |

## 3. Runs and sessions

- **Pass `runId`, `graphConfig` and a provider key from the environment.** The single-agent
  shape is `graphConfig: { type: 'standard', instructions, llmConfig: { provider, model, apiKey } }`
  (`Providers.OPENAI`, `Providers.ANTHROPIC`, ...); `tools` and `additional_instructions` sit
  beside `instructions`. `instructions` is the stable, cacheable system prompt;
  `additional_instructions` is the dynamic tail with no cache markers. Then
  `await run.processStream({ messages }, { runId, streamMode: 'values', version: 'v2' })`.
  With `returnContent: true` it resolves to the content parts; otherwise register handlers.
- **A resolved `processStream()` is not success.** Check `run.getInterrupt()` (a pending
  `tool_approval` or `ask_user_question`), `run.getHaltReason()` (`handoff_limit`, hook blocks)
  and the abort signal before you treat the output as final.
- **Sessions:** `createAgentSession({ checkpointing: true, graphConfig })`, then
  `await session.run('...')` returns `{ text, content, messages, usage, steps, interrupt,
  haltedReason, runId, threadId }`; `session.stream()` yields typed events
  (`message.delta`, `tool.started`, `run.completed`, ...). `session.sessionPath` is the durable
  `.jsonl`; with `checkpointing` on, the session injects a shared LangGraph checkpointer
  (`MemorySaver` unless you pass one) and records checkpoint ids in the journal. Pass `ephemeral:
  true` to skip the file.
- **Human in the loop:** set `humanInTheLoop: { enabled: true }` in the run config. A paused run
  reports its interrupt; resume with `run.resume(decisions, config)` or
  `session.resumeInterrupt(decisions)`, where each decision is `{ type: 'approve' }`,
  `{ type: 'reject', reason? }`, `{ type: 'edit', updatedInput }` or `{ type: 'respond',
  responseText }`, as an array or a map keyed by tool call id. Rebuild the same graph with the
  same checkpointer and `thread_id`; approvals belong to the checkpoint, not to the old `Run`
  object (`docs/tool-approval-replay.md`).
- **Custom providers:** `registerProvider({ provider: 'acme', model: AcmeChatModel, family:
  'openai' })` from `@librechat/agents/provider-registration`, once per process, before any
  config names it. Duplicate names throw; the returned function unregisters. Declaration-merge
  `CustomProviderOptionsMap` to type the options.

## 4. Tools, deferral, tool search and skills

A **tool registry** is one `Map<string, LCTool>` of every tool the agent may ever call, bound or
not, keyed by name. The SDK reads it as `toolRegistry` on the agent; LibreChat builds it from
`librechat.yaml` MCP servers, actions and system tools. Keep schemas in one place and derive
everything (binding, search, approval policy, telemetry) from it.

- **Deferral:** an `LCTool` with `defer_loading: true` stays out of the model's `tools` until
  `tool_search` returns it; the graph then marks it discovered and rebinds for the next model
  call. Persist `run.getDiscoveredTools()` and pass it back as `discoveredTools` on the next turn
  so the model doesn't search twice. The definition and the registry entry must be the same
  object. Never defer `tool_search` itself.
- **`createToolSearch({ mode: 'local', toolRegistry })`.** The default `mode` is
  `'code_interpreter'`, which ships a regex search to LibreChat's Code API sandbox; outside
  LibreChat use `'local'`, an in-process Okapi BM25 over tool names (doubled), descriptions and,
  optionally, parameter names. MCP tools are named `toolName_mcp_serverName`
  (`Constants.MCP_DELIMITER`), which is how the `mcp_server` filter works; a server filter with no
  query lists that server's tools without loading them. The result is `content_and_artifact`:
  text for the model plus `{ tool_references: [{ tool_name, match_score, matched_field,
  snippet }], metadata }`. Exact schema and ranking rules: references/tool-registries.md.
- **Skills:** the SDK exports `SkillToolDefinition` (`name: 'skill'`, args `skillName`, `args`)
  and `formatSkillCatalog(entries, opts)`, which renders `## Available Skills` as
  `- name: description` lines inside a budget (1% of a 200k context, 250 chars per entry, then
  proportional truncation, then names only). The host appends the catalog to
  `additional_instructions` and answers the `skill` call by injecting the skill's body; the SDK
  creates no tool instance. LibreChat caps the list with `endpoints.agents.skills.maxCatalogSkills`.
- **Approvals and policy stay in the host:** hooks (`PreToolUse` etc.) and `humanInTheLoop`
  decide; a registry entry carries no credentials.

## 5. Multi-agent

`graphConfig: { type: 'multi-agent', agents, edges, entryAgentId, maxHandoffs }`. A handoff edge
creates a `transfer_to_<agent>` tool; `edgeType: 'direct'` fans out or joins in parallel with no
tool. Set `maxHandoffs` separately from `recursionLimit`; an overrun halts with
`handoff_limit`. After the stream, `run.getHandoffOutcome()` is `candidate` only for an explicit
`handoffScope: 'conversation'` edge in an unambiguous run; the host decides whether to switch the
conversation's agent. Subagents (`Run.create({ subagentContext })`) get their own execution
identity and tool-session partition; the host authorizes them in `prepare()` (`docs/subagent-context.md`).

## 6. Registries beyond the SDK

- **Anthropic and Claude Code use the same deferral idea:** the Messages API takes
  `defer_loading: true` on a tool plus a `tool_search_tool_bm25_20251119` or
  `tool_search_tool_regex_20251119` server tool, and rejects a request where every tool is
  deferred; Claude Code's own `ToolSearch` loads a deferred tool's schema by `select:<name>` or a
  keyword query before the tool can be called. Confirm the API tool names in the `claude-api`
  skill before writing them.
- **MCP Registry** (`https://registry.modelcontextprotocol.io`, read-only over HTTP, current path
  prefix `/v0.1`): `GET /v0.1/servers?search=<3+ chars>&version=latest&limit=<n>&cursor=<next>`
  and `GET /v0.1/servers/{url-encoded name}/versions/latest`. Results are ordered by name then
  version string as text (`1.10.0` before `1.2.0`), so always pass `version=latest` and check
  `_meta["io.modelcontextprotocol.registry/official"].status == "active"`, because a deprecated
  version can still be the latest. `updated_since=<RFC3339>` drives incremental sync. OpenAPI at
  `/openapi.yaml`; publishing only through the `mcp-publisher` CLI. Shapes and a `curl` recipe:
  references/tool-registries.md.
- **LibreChat registers tools in `librechat.yaml`:** `mcpServers.<name>` with `type`
  (`stdio`, `sse`, `streamable-http`), `command`/`args` or `url`, `headers`, `timeout`,
  `requiresOAuth`, and `oauthToolCatalog` (tools offered to `tool_search` before sign-in).
  Skills come from three places: inline Skills through `GET/POST/PATCH/DELETE
  /api/agents/v1/skills` (management auth, versioned updates), git-synced skills through
  `skillSync.github`, and deployment skills in `skill/<name>/SKILL.md` (read-only, loaded at
  startup). SDK runtimes register as `endpoints.agents.sdkRuntimes.<id>` with `module` or
  `remote: { url, secret }` and an agent created with `sdk_runtime: { id, protocolVersion: 1 }`.

## Check before you hand it back

```bash
npm ls @librechat/agents @langchain/core @langchain/langgraph   # one copy each, pinned
node --version                                                  # 24+
npx tsc --noEmit
```

Then, against a real provider key from the environment:

- A session `run()` returns `text`, and a second `run()` on the same session continues the thread.
- With one deferred tool, the transcript shows `tool_search` followed by the tool's own call, and
  `run.getDiscoveredTools()` names it.
- With `humanInTheLoop` on and a tool that asks, `getInterrupt()` is set, and `resume` with an
  `approve` decision finishes the turn without re-running completed siblings.
- The skill catalog in the rendered system prompt fits its budget (no dropped descriptions in
  the logs).
