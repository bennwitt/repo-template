# @librechat/agents: API shapes

Quoted from `LibreChat-AI/agents` `main` at `20b1fad` (2026-11-18, package version 4.2.10).
Before you rely on one, read the same file at your pinned tag
(`gh api 'repos/LibreChat-AI/agents/contents/<path>?ref=v4.2.2' -H 'Accept: application/vnd.github.raw'`).

## Package

- `package.json`: `"engines": { "node": ">=24.0.0" }`; exact pins on `@langchain/core` (1.2.8 at
  4.2.10) and `@langchain/langgraph` (1.4.8); `okapibm25` powers local tool search; `zod` 4.
- Subpath exports: `.`, `./provider-registration`, `./openai`, `./responses`, `./runtime`,
  `./rerank`, `./decisions`, `./llm/{anthropic,bedrock,google,mistral,openai,openrouter,vertexai}`
  and `./langchain/*` re-exports.
- `src/index.ts` re-exports `./tools/SkillTool`, `./tools/skillCatalog`, `./tools/ToolSearch`,
  `./session`, and `registerProvider` from `./provider-registration`.

## Run (`src/run.ts`, `src/types/run.ts`)

```ts
import { HumanMessage } from '@langchain/core/messages';
import { Providers, Run } from '@librechat/agents';

const run = await Run.create({
  runId: crypto.randomUUID(),
  graphConfig: {
    type: 'standard',
    instructions: 'You are a helpful assistant.',
    llmConfig: {
      provider: Providers.OPENAI,
      model: 'gpt-4o-mini',
      apiKey: process.env.OPENAI_API_KEY,
    },
  },
  returnContent: true,
});

const content = await run.processStream(
  { messages: [new HumanMessage('Hello')] },
  {
    runId: crypto.randomUUID(),
    streamMode: 'values',
    version: 'v2',
  }
);
```

Signatures:

```ts
static async create<T extends t.BaseGraphState>(config: t.RunConfig): Promise<Run<T>>
async processStream(
  inputs: t.IState | Command,
  callerConfig: t.RunStreamConfig,
  streamOptions?: t.EventStreamOptions
): Promise<MessageContentComplex[] | undefined>
async resume<TResume = t.ToolApprovalDecision[] | t.ToolApprovalDecisionMap>(
  resumeValue: TResume,
  callerConfig: t.RunStreamConfig,
  streamOptions?: t.EventStreamOptions,
  commandOptions?: Pick<ConstructorParameters<typeof Command>[0], 'update' | 'goto'>
): Promise<MessageContentComplex[] | undefined>
getInterrupt<TPayload = t.HumanInterruptPayload>()
getHaltReason(): string | undefined
getHandoffOutcome(): t.HandoffOutcome | undefined
getDiscoveredTools(agentId?: string): string[]
getRunMessages(): BaseMessage[] | undefined
```

`RunConfig` (selected fields): `runId: string`; `graphConfig: LegacyGraphConfig |
StandardGraphConfig | MultiAgentGraphConfig`; `customHandlers?: Record<string, EventHandler>`;
`clientDelegatedToolNames?`; `subagentContext?`; `onSubagentResolutionFailure?`; `hooks?:
HookRegistry`; `humanInTheLoop?: HumanInTheLoopConfig`; `streamLimits?`; `returnContent?:
boolean`; `tokenCounter?`; `indexTokenCountMap?`; `calibrationRatio?`; `initialSessions?`;
`toolOutputReferences?`; `eagerEventToolExecution?`.

Graph configs:

- `LegacyGraphConfig` is the README shape: `type?: 'standard'`, `llmConfig`, `signal?`, `tools?`,
  plus the `AgentInputs` fields (`instructions`, `additional_instructions`, `toolRegistry`,
  `toolDefinitions`, `discoveredTools`, `maxContextTokens`, ...). `Run` splits `llmConfig` into
  `provider` and `clientOptions` and builds one agent with `agentId: 'default'`.
- `StandardGraphConfig`: `{ type?: 'standard'; signal?; compileOptions?; agents: AgentInputs[] }`.
- `MultiAgentGraphConfig`: `{ type: 'multi-agent'; compileOptions?; agents: AgentInputs[]; edges:
  GraphEdge[]; entryAgentId?: string; maxHandoffs?: number }`.

`AgentInputFields` (`src/types/graph.ts`): `agentId: string`, `endpoint?`, `codeSessionKey?`,
`name?`, `toolEnd?`, `toolMap?`, `tools?: GraphTools`, `instructions?: string` ("Stable/cacheable
system instructions"), `streamBuffer?`, `maxContextTokens?`, `langfuse?`,
`additional_instructions?: string` ("Dynamic system tail appended after stable instructions
without provider cache markers"), `reasoningKey?`, `useLegacyContent?`, `toolRegistry?:
Map<string, LCTool>` ("Tool definitions for all tools, including deferred and programmatic. Used
for tool search and programmatic tool calling"), `toolDefinitions?: LCTool[]` (event-driven
execution: ToolNode dispatches `ON_TOOL_EXECUTE` instead of invoking), `discoveredTools?:
string[]` ("Tool names discovered from previous conversation history"), `summarizationEnabled?`.

## Human in the loop (`src/types/hitl.ts`)

```ts
export interface HumanInTheLoopConfig {
  enabled?: boolean;                         // default false
  backgroundPausePolicy?: 'deny' | 'reject'; // background children cannot pause
}
export type ToolApprovalDecision =
  | { type: 'approve' }
  | { type: 'reject'; reason?: string }
  | { type: 'edit'; updatedInput: Record<string, unknown> }
  | { type: 'respond'; responseText: string };
export type ToolApprovalDecisionMap = Record<string, ToolApprovalDecision>;
export type HumanInterruptType = 'tool_approval' | 'ask_user_question';
```

Replay contract (`docs/tool-approval-replay.md`): an approval belongs to an execution, not to a
JavaScript object or the current hook registry. `Run.resume` reads private evidence from the
checkpoint; a fresh ToolNode restores completed siblings and consumes the reviewed decision;
changed proposals fail closed. Standalone callers must supply a stable `configurable.thread_id`.
Not exactly-once for external side effects: a crash between the side effect and the checkpoint
commit is ambiguous, so tools that need retry safety use their own idempotency key.

## Sessions (`src/session/`)

```ts
import { Providers, createAgentSession } from '@librechat/agents';

const session = await createAgentSession({
  checkpointing: true,
  graphConfig: {
    type: 'standard',
    instructions: 'You are a concise coding assistant.',
    llmConfig: { provider: Providers.OPENAI, model: 'gpt-4o-mini', apiKey: process.env.OPENAI_API_KEY },
  },
});
const result = await session.run('Summarize this repository.');
console.log(result.text);
console.log(session.sessionPath); // durable .jsonl session file
```

`AgentSessionConfig` is either `{ runConfig: RunConfig, ... }` or a `RunConfig` spread with
`runId` optional, plus `cwd?`, `sessionPath?`, `sessionId?`, `name?`, `ephemeral?`,
`checkpointing?: boolean | { enabled?: boolean; checkpointer?: BaseCheckpointSaver }`.

Methods: `run(input, options?)`, `stream(input, options?)` (returns an `AsyncIterable` of
`AgentSessionStreamEvent` with `toTextStream()` and `finalResult()`), `resumeInterrupt(value,
options?)`, `resumeSession(pathOrId?)`, `clone(options?)`, `fork(entryId, { position:
'before' | 'at' })`, `branch(...)`, `compact({ instructions?, retainRecentTurns? })`,
`getSessionStore()`, `sessionPath`. `AgentSessionInput` is `string | BaseMessage |
BaseMessage[] | IState`. `AgentSessionRunOptions`: `runId?`, `threadId?`, `config?` (with
`version?: 'v1' | 'v2'` and `durability?`), `streamOptions?`.

`AgentSessionRunResult`: `{ text, content, messages, usage: { inputTokens, outputTokens,
totalTokens }, steps, interrupt, haltedReason, runId, threadId }`.

Stream event types: `run.started`, `message.delta`, `reasoning.delta`, `tool.started`,
`tool.delta`, `tool.completed`, `step.finished`, `usage.updated`, `run.completed`, `run.failed`,
`run.interrupted`, `run.halted`; each carries `sequence`, `runId`, `threadId`, `timestamp`, `data?`.

JSONL journal: a `SessionHeader` `{ type: 'session', version: 1, id, timestamp, cwd, name?,
parentSession? }` followed by entries of type `message`, `summary`, `compaction`, `checkpoint`
(`{ provider: 'langgraph', source: 'run' | 'resume' | 'reset', threadId, runId?, checkpointId?,
checkpointNs?, parentCheckpointId? }`), `label`, `run_event`, `session_state`, each with `id`,
`parentId` and `timestamp` (a tree, so forks share a prefix). The README: "JSONL is the durable
journal; the graph remains the execution engine." With `checkpointing` enabled or
`humanInTheLoop.enabled`, the session supplies a `MemorySaver` unless a `checkpointer` is given.

## Provider registration (`src/provider-registration.ts`, ADR 0003)

```ts
import { registerProvider } from '@librechat/agents/provider-registration';
import type { LLMConfig } from '@librechat/agents';

declare module '@librechat/agents/provider-registration' {
  interface CustomProviderOptionsMap { acme: AcmeOptions; }
}
const unregister = registerProvider({ provider: 'acme', model: AcmeChatModel, family: 'openai' });
const llmConfig: LLMConfig = { provider: 'acme', apiKey: process.env.ACME_API_KEY!, model: 'acme-chat' };
```

`ProviderRegistrationOptions`: `provider: string`, `model: new (config) => BaseChatModel`,
`family?: 'openai' | 'anthropic' | 'bedrock' | 'google' | 'mistral' | 'generic'`,
`manualToolStream?: boolean`, `strictAlternation?: boolean`. Register once per process before
the provider is used; duplicate names are rejected; `unregister()` removes only that
registration. Family governs shared protocol behavior (thinking detection, output-token option
names, atomic tool-call handling); bindings are process-local and do not cross workers.

## Multi-agent (`docs/multi-agent-patterns.md`)

```ts
const edges: t.GraphEdge[] = [
  { from: 'classifier', to: ['technical_expert', 'business_expert'], edgeType: 'handoff',
    condition: (state) => /* return an agent id */ 'technical_expert' },
  { from: 'researcher', to: ['analyst1', 'analyst2'], edgeType: 'direct' },   // fan-out
  { from: ['analyst1', 'analyst2'], to: 'summarizer', edgeType: 'direct' },   // fan-in
];
```

- Single-to-single edges default to handoff; single-to-multiple default to parallel; edges with
  `condition` are always handoff; fan-in must set `edgeType: 'direct'` explicitly.
- Handoff edges create `transfer_to_<agent>` tools; parallel edges create graph edges and share
  the same `messages` state.
- `maxHandoffs` is shared by all members and branches within one logical turn; zero forbids
  handoffs; an oversized batch throws `HandoffLimitError` and `getHaltReason()` reports
  `handoff_limit`.
- `handoffScope: 'conversation'` is trusted graph configuration. `getHandoffOutcome().status` is
  `candidate` (with `agentId` and `transitionId`), `unchanged`, `ambiguous` (parallel execution)
  or `incomplete` (interruption, failure, budget). The next user turn is a fresh run with
  `entryAgentId` set; to resume a paused run rebuild the original graph and call `Run.resume()`.
- Subagents: `Run.create({ subagentContext })` with `prepare(input)` (authorize, supply
  `messages`, `configurable`, `agentSessions`) and `complete(input, result)`; the SDK exports
  `SUBAGENT_CONTEXT_VERSION = 1`. `onSubagentResolutionFailure` maps a private startup error to
  one of `workspace_unavailable`, `agent_unavailable`, `model_unavailable`,
  `configuration_changed`, `unknown`.

## Skills (`src/tools/SkillTool.ts`, `src/tools/skillCatalog.ts`, `src/types/skill.ts`)

```ts
export type SkillCatalogEntry = { name: string; description: string; displayTitle?: string };
export type SkillCatalogOptions = {
  contextWindowTokens?: number; // Default: 200_000
  budgetPercent?: number;       // Default: 0.01 (1%)
  maxEntryChars?: number;       // Default: 250
  minDescLength?: number;       // Default: 20
  charsPerToken?: number;       // Default: 4
};
export function formatSkillCatalog(skills: SkillCatalogEntry[], opts?: SkillCatalogOptions): string
```

Output is `## Available Skills\n\n- name: description\n...`. Truncation ladder: cap each entry
at `maxEntryChars`; if the whole catalog exceeds `contextWindowTokens * budgetPercent *
charsPerToken` characters, truncate descriptions proportionally; if that leaves fewer than
`minDescLength` characters each, fall back to names only, dropping trailing entries that
still don't fit.

`SkillToolDefinition = { name: 'skill', description, parameters }` with properties `intent`,
`skillName` (kebab-case, "Must match a name from the 'Available Skills' section") and `args`
(freeform string); `required: ['skillName']`. The description tells the model to invoke a
matching skill before attempting the task, not to re-invoke an active skill, and never to guess
names. LibreChat (`packages/api/src/agents/skills.ts`) appends the catalog to
`agent.additional_instructions`, registers the definition, and intercepts the call through
`ON_TOOL_EXECUTE` ("No tool instance is created — SkillTool is event-driven only").
