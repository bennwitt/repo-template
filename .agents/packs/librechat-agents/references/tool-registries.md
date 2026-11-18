# Tool registries for LLM agents

Checked 2026-11-18 against `LibreChat-AI/agents` `main` `20b1fad` (`src/tools/ToolSearch.ts`,
`src/types/tools.ts`), `LibreChat-AI/LibreChat` `main` `d4e85d2` (`librechat.example.yaml`,
`docs/skills-management-api.md`, `skill/README.md`, `docs/sdk/agents.md`,
`docs/tool-approval-modes.md`, `packages/api/src/agents/deferral.ts`) and
`modelcontextprotocol/registry` `main` `115f852` (`docs/reference/api/official-registry-api.md`,
`docs/reference/api/openapi.yaml`, `docs/reference/cli/commands.md`), plus a live call to the
registry. Re-read the file at your version before relying on a shape.

## Why a registry

A registry is the one map from tool name to definition (`name`, `description`, JSON Schema
`parameters`, plus policy flags). Everything else derives from it:

- **Binding:** which definitions go into the model's `tools` this turn.
- **Discovery:** what `tool_search` ranks when the model asks.
- **Budget:** each bound schema costs prompt tokens on every call; deferring the long tail and
  loading on demand keeps the per-turn cost flat as the catalog grows.
- **Policy:** approval mode, caller restrictions (`allowed_callers: ['direct' |
  'code_execution']`), server attribution (`serverName`, `toolType: 'builtin' | 'mcp' |
  'action'`) all hang off the same entry, so the host never guesses from a tool name.
- **Provenance:** the entry says where a tool came from (which MCP server, which action), which
  is what approval UIs and audit logs show.

Keep credentials out of it. The registry says a tool exists and what it takes; the host resolves
secrets at call time.

## `@librechat/agents` `LCTool` and `ToolSearch`

```ts
export type LCTool = {
  name: string;
  description?: string;
  parameters?: JsonSchemaType;
  /** When true, tool is not loaded into context initially (for tool search) */
  defer_loading?: boolean;
  allowed_callers?: AllowedCaller[];          // 'direct' | 'code_execution'
  responseFormat?: 'content' | 'content_and_artifact';
  serverName?: string;                        // Server name for MCP tools
  toolType?: 'builtin' | 'mcp' | 'action';
};
export type LCToolRegistry = Map<string, LCTool>;

export type ToolSearchParams = {
  toolRegistry?: LCToolRegistry;
  onlyDeferred?: boolean;                     // default true
  baseUrl?: string;                           // Code API base, code_interpreter mode only
  mode?: 'code_interpreter' | 'local';        // default 'code_interpreter'
  mcpServer?: string | string[];
  mcpNameFormat?: 'full' | 'base';            // default 'full' (tool_mcp_server)
};
```

Model-facing schema (`ToolSearchToolSchema`): `query` (string, `maxLength: 200`, default `''`;
in `local` mode "Case-insensitive substring matching", in `code_interpreter` mode a regex),
`fields` (array of `'name' | 'description' | 'parameters'`, default `['name', 'description']`),
`max_results` (integer 1-50, default 5), `mcp_server` (string or array; "If provided without a
query, lists all tools from those servers"). All optional. Tool name is `Constants.TOOL_SEARCH`
= `'tool_search'`; response format `content_and_artifact`.

How it works (`createToolSearch`):

- The description the model sees ends with `Deferred tools (search to load; … = has params,
  search first):` and one line per server, `server: tool1, tool2(…)`, non-MCP tools under
  `other`. So the model already knows the names; search is how it loads a schema.
- MCP tool names are `toolName_mcp_serverName` (`Constants.MCP_DELIMITER = '_mcp_'`).
  `extractMcpServerName` splits on that; `canonicalizeServerName` folds case and separators but
  never drops a character, so `clickhouse-cloud` matches `ClickHouse_Cloud`.
- `local` mode, `performLocalSearch`: tokenize (split on non-alphanumerics and camelCase, lower
  case); the document is the name with underscores as spaces, included twice, then the
  description, then parameter names if requested; Okapi BM25 with `k1: 1.5, b: 0.75`, scores
  normalized to the best hit; an exact full-name or base-name match, or a prefix of the
  identifier, is ranked above BM25. An empty query returns all tools alphabetically up to
  `max_results`.
- `code_interpreter` mode generates a JavaScript search script and runs it in LibreChat's Code
  API sandbox (`getCodeBaseURL()`), with regex sanitizing (`MAX_PATTERN_LENGTH = 200`,
  nesting-depth and nested-quantifier checks, 5 s timeout). Use `local` anywhere without that
  sandbox.
- Result artifact: `{ tool_references: [{ tool_name, match_score, matched_field, snippet }],
  metadata: { total_searched, pattern, error?, available_mcp_servers?, unmatched_mcp_servers?,
  idle_mcp_servers? } }`. A server filter that matches nothing reports the servers that exist
  instead of failing silently.
- Loading: the agent context's `markToolsAsDiscovered(names)` adds names to
  `discoveredToolNames`, marks the system runnable stale and recounts schema tokens, so the next
  model call binds them. `Run.getDiscoveredTools()` snapshots the set for persistence;
  `AgentInputs.discoveredTools` pre-marks them on a later turn.
- The LibreChat host (`packages/api/src/agents/deferral.ts`) keeps `tool_search`, the
  programmatic bash tool, the background-task poll tool, `skill` and `ask_user_question`
  non-deferrable, marks the agent's selected tools in one pass over the final definitions, and
  requires "A deferred definition and its registry entry must be the SAME object".

## Anthropic API and Claude Code

- Messages API: mark a tool `defer_loading: true` and declare a server tool of type
  `tool_search_tool_bm25_20251119` (name `tool_search_tool_bm25`) or
  `tool_search_tool_regex_20251119` (name `tool_search_tool_regex`); results arrive as
  `tool_search_tool_result` blocks. The search tool itself must not be deferred, and at least one
  tool must stay non-deferred or the API returns 400 `All tools have defer_loading set`. These
  names come from the `claude-api` skill (cached 2026-11-03); confirm against the live docs
  before writing them.
- Claude Code: tools not loaded at session start appear by name only. Its `ToolSearch` tool
  fetches their schemas with `select:<Name>[,<Name>...]`, a keyword query, or `+word` to require
  a term in the name, and the tool becomes callable only after its schema appears. Same
  pattern: names are cheap, schemas are loaded on demand.

## The official MCP Registry

Base URL `https://registry.modelcontextprotocol.io` (staging:
`https://staging.registry.modelcontextprotocol.io`). Interactive docs at `/docs`, OpenAPI at
`/openapi.yaml` (servers and publish endpoints only; `/v0.1/validate`, `/v0.1/ping`,
`/v0.1/version` and `/v0.1/health` are not in it). Reads need no auth. Publishing needs a
namespace login (GitHub OAuth or OIDC for `io.github.*`, DNS or HTTP verification for
`com.example.*`) and happens only through the `mcp-publisher` CLI: a pull request against the
registry repository does not publish anything.

Endpoints:

| Call | Notes |
| --- | --- |
| `GET /v0.1/servers?search=<text>&version=latest&updated_since=<RFC3339>&limit=<n>&cursor=<c>` | One record per server version. `search` is a case-insensitive substring on names and must be at least 3 characters after trimming (else HTTP 422). `include_deleted` defaults false, but is forced true when `updated_since` is set. |
| `GET /v0.1/servers/{serverName}/versions/latest` | `serverName` URL-encoded, e.g. `io.github.example%2Fweather`. Use this when you know the name. |
| `GET /v0.1/servers/{serverName}/versions/{version}` | One version; `include_deleted` optional. |
| `GET /v0.1/servers/{serverName}/versions` | Version history. |
| `GET /v0.1/version`, `GET /v0.1/ping`, `GET /v0.1/health` | Service info. |
| `POST /v0.1/validate` | Validates a `server.json` without publishing (`mcp-publisher validate`). |
| `POST /v0.1/publish`, `PATCH .../status`, `PUT .../versions/{version}` | Authenticated writes. |

Ordering and status rules, verbatim from the API doc:

- "Results are ordered by server name, then by version string, both ascending. Version strings
  are compared as text, not by semantic version or publication date; for example, `1.10.0`
  sorts before `1.2.0`. Do not treat the first result for a server as its latest version."
- "To retrieve only the latest version of each matching server, pass `version=latest`. Returned
  records have `_meta["io.modelcontextprotocol.registry/official"].isLatest` set to `true`. Keep
  the same filters when following `metadata.nextCursor` to subsequent pages."
- "Deprecating a version does not, by itself, remove its `isLatest` flag... Clients that display
  only active servers must also check
  `_meta["io.modelcontextprotocol.registry/official"].status == "active"`."
- Status values: `active`, `deprecated` (still listed, with a message), `deleted` (hidden unless
  `include_deleted=true`).

Response shape, from a live call on 2026-11-18
(`curl -fsS 'https://registry.modelcontextprotocol.io/v0.1/servers?search=filesystem&version=latest&limit=2'`):

```json
{
  "servers": [
    {
      "server": {
        "$schema": "https://static.modelcontextprotocol.io/schemas/2025-09-29/server.schema.json",
        "name": "com.pulsemcp/remote-filesystem",
        "description": "MCP server for remote filesystem operations on cloud storage (Google Cloud Storage).",
        "repository": { "url": "https://github.com/pulsemcp/mcp-servers", "source": "github", "subfolder": "experimental/remote-filesystem" },
        "version": "0.1.5",
        "packages": [
          {
            "registryType": "npm",
            "registryBaseUrl": "https://registry.npmjs.org",
            "identifier": "remote-filesystem-mcp-server",
            "version": "0.1.5",
            "runtimeHint": "npx",
            "transport": { "type": "stdio" },
            "runtimeArguments": [{ "type": "positional", "value": "-y" }],
            "environmentVariables": [
              { "description": "Google Cloud Storage bucket name.", "isRequired": true, "name": "GCS_BUCKET" },
              { "description": "Service account private key for inline credentials.", "isSecret": true, "name": "GCS_PRIVATE_KEY" }
            ]
          }
        ]
      },
      "_meta": {
        "io.modelcontextprotocol.registry/official": {
          "status": "active",
          "statusChangedAt": "2026-06-26T14:07:53.723164Z",
          "publishedAt": "2026-06-26T14:07:53.723164Z",
          "updatedAt": "2026-06-26T14:07:53.723164Z",
          "isLatest": true
        }
      }
    }
  ],
  "metadata": { "nextCursor": "io.github.Digital-Defiance/mcp-filesystem:0.1.9", "count": 2 }
}
```

(The sample is abridged to one server and two environment variables.) A remote-only server has
a `remotes` array instead of `packages`. Package `version` must be exact; ranges are rejected.
`environmentVariables[].isSecret` tells you which values to source from the environment and
never write into a config file.

Recipe for a registry client:

```bash
Q=filesystem
curl -fsS "https://registry.modelcontextprotocol.io/v0.1/servers?search=$Q&version=latest&limit=50" \
  | jq -r '.servers[] | select(._meta["io.modelcontextprotocol.registry/official"].status == "active")
           | [.server.name, .server.version, (.server.packages[0].registryType // "remote")] | @tsv'
# follow .metadata.nextCursor with &cursor=<value> and the same filters
curl -fsS "https://registry.modelcontextprotocol.io/v0.1/servers/$(printf %s 'io.github.example/weather' | jq -sRr @uri)/versions/latest"
```

`mcp-publisher` (publishing only): install with `brew install mcp-publisher` or the release
tarball from `github.com/modelcontextprotocol/registry/releases`; `mcp-publisher init` writes a
`server.json`, `mcp-publisher login github` (or `github-oidc`, `dns`, `http`) authenticates,
`mcp-publisher validate` and `mcp-publisher publish` follow. Tokens come from the login flow or
the environment, never from a file in the repository.

## How LibreChat registers tools and skills

### MCP servers in `librechat.yaml` (`mcpServers`)

Shapes from `librechat.example.yaml`:

```yaml
mcpServers:
  everything:
    # type: sse # type can optionally be omitted
    url: http://localhost:3001/sse
    timeout: 60000  # default timeout for MCP servers
  coordinated-oauth:
    type: streamable-http
    url: https://mcp.example.com/mcp
    requiresOAuth: true
    # oauthPrompt: on_use        # ask at first tool call, only when every selected tool is deferred
    # oauthToolCatalog:          # tools offered to tool search before the user signs in
    #   - name: read_sheet
    #     description: Read the values in a spreadsheet range
    #     inputSchema: { type: object, properties: { range: { type: string } }, required: [range] }
  private-openid:
    type: streamable-http
    url: https://mcp.example.com/mcp
    headers:
      Authorization: "Bearer {{LIBRECHAT_OPENID_ACCESS_TOKEN}}"
    requestHeaders:                      # sent only during a chat turn
      X-Conversation-Id: "{{LIBRECHAT_BODY_CONVERSATIONID}}"
      X-Agent-Id: "{{LIBRECHAT_AGENT_ID}}"
  filesystem:
    command: npx                          # stdio when command is set
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/LibreChat/"]
    iconPath: /home/user/LibreChat/client/public/assets/logo.svg
```

Other keys seen there: `proxy`, `oauthRefreshCoordination`, `oauthRefreshWaitTimeout`,
`oauthPersistenceWaitTimeout`. `interface.mcpServers` holds `toolsRefreshInterval` and
`statusRefreshInterval` plus the `use`/`create`/`share`/`public` permissions; `mcpSettings` holds
domain restrictions and `apps: true` for MCP Apps; `mcpAppSandbox` holds the sandbox limits
(`docs/mcp-apps.md`). Every MCP tool lands in the agent's registry as `<tool>_mcp_<server>`, and
each MCP tool row in the agent builder exposes the defer, programmatic, background and intent
options next to the approval shield (`docs/tool-approval-modes.md`: Inherited, Always ask, Always
approve, Ask once per chat, Ask once then always approve; activation under
`endpoints.agents.toolApproval`).

### Skills

Three sources, all read into the same catalog:

1. **Inline Skills via the management API** (`docs/skills-management-api.md`), mounted with the
   Agent management auth (`endpoints.agents.managementApi.auth`), never browser sessions:

   | Method | Path |
   | --- | --- |
   | GET | `/api/agents/v1/skills` (`limit`, `cursor`) |
   | POST | `/api/agents/v1/skills` |
   | GET / PATCH / DELETE | `/api/agents/v1/skills/:id` |
   | GET | `/api/agents/v1/skills/:id/files` |
   | GET / PUT / DELETE | `/api/agents/v1/skills/:id/files/*relativePath` |

   Create: `{ "name": "query-review", "description": "...", "body": "..." }`. Update needs
   `expectedVersion` from the latest read (stale version: HTTP 409, `error.code: "conflict"`).
   Editable fields: `name`, `displayTitle`, `description`, `body`, `frontmatter`, `category`,
   `alwaysApply`. File writes take `{ "content": "..." }` up to 1 MiB at a relative path such as
   `references/guide.md`; update `SKILL.md` through `body`, not the file route; a file write also
   bumps the version. Lists use the Agent envelope `object`, `data`, `first_id`, `last_id`,
   `has_more`, `after`. Pass skill ids in an Agent's `skills` field to assign them.
2. **Git-synced skills**: `skillSync.github.sources[]` with `owner`, `repo`, `ref`, `paths`,
   `skillDiscoveryDepth`, `token: '${GITHUB_SKILLS_TOKEN}'` (a read-only fine-grained token
   referenced from `.env`), optional `tenantId`. Readable through the API, not writable.
3. **Deployment skills** in `skill/<name>/SKILL.md` (with `references/` beside it): "loaded at
   server startup, exposed read-only to all users with Skills enabled, and are not persisted as
   Skill documents in MongoDB" (`skill/README.md`).

`endpoints.agents.capabilities` must include `skills` (and `deferred_tools` for deferral); the
default list in the example does. `endpoints.agents.skills.maxCatalogSkills` caps the
model-visible catalog. A skill with `alwaysApply: true` is primed into every turn instead of
waiting for a `skill` call.

### SDK runtimes (`docs/sdk/agents.md`)

```yaml
endpoints:
  agents:
    sdkRuntimes:
      schema-advisor:
        module: ./runtimes/schema-advisor.cjs   # or remote: { url: wss://..., secret: '${SDK_SECRET}' }
        roles: [ADMIN]
```

```js
const { Run } = require('@librechat/agents');
module.exports = {
  protocolVersion: 1,
  async createRun({ config, identity }) {
    return Run.create(config); // keep the host's handlers, hooks, signal, checkpointing, policy
  },
};
```

Register the agent with `POST /api/agents/v1/agents` and `"sdk_runtime": { "id":
"schema-advisor", "protocolVersion": 1 }`; `sdk_runtime: null` returns it to native execution.
Modules are trusted server code; use the server's installed SDK as a peer dependency so the Run
shares one SDK instance. Remote workers need SDK 4.2.4+ for host tool execution and 4.2.7+ for
the provider-text service; the doc's parity matrix lists what is not yet verified remotely.
