# Executable MCP development baseline

Protocol: **2026-07-28**, with explicit **2025-11-25** compatibility tests. Reviewed package pins
and publication dates live in [the development manifest](../../.agents/mcp-development.json).
The Python and TypeScript lockfiles also record transitive dependencies; they do not change any
application's dependencies. Node 22.22.0 meets Inspector 2.12's >=22.19 requirement. Python CI
uses 3.12. Review newer pins with `repo-template globals --upstream`, update these fixtures and
locks, and rerun their checks before changing the baseline. No automatic application migration.

## Run

Run each block from its stated project directory, not the repository root:

```bash
cd examples/mcp/python
uv sync --locked --dev --python 3.12
uv run pytest
```

```bash
cd examples/mcp/typescript
npm ci --ignore-scripts
npm run build
npm test
npx --no-install @modelcontextprotocol/inspector --help
```

Use the locked Inspector for interactive inspection when needed; its startup/help check does
not replace the transport tests. Local HTTP tests need loopback sockets and may require running
outside an agent's network-isolating sandbox. They use no external services or credentials.
Format explicit project-owned files only; never recursively format through `.agents` or `.claude`
skill links. The suite's synthetic identities and tokens are fixtures, not deployment defaults.

## What is executable

- [Python server](python/src/mcp_example/server.py): bounded pagination, ownership, masked errors,
  cancellable work and a FastAPI mount with lifespan and Host/Origin protection.
- [Official SDK server](python/src/mcp_example/sdk_server.py): a minimal src-layout v2 server.
- [Python tests](python/tests/test_servers.py): modern/legacy memory, stdio and real HTTP clients;
  JWT signature/issuer/audience/expiry/scope failures; ownership; cleanup; deterministic agent
  workflow with results checked against independent fixture state.
- [TypeScript server](typescript/server.ts): factory-based modern and legacy serving, schema
  validation, node HTTP adapter, scoped bearer middleware and cancellation propagation.
- [TypeScript tests](typescript/test.ts): real transports and authentication boundaries, typed
  results, cancellation, and a pinned codemod run on a temporary v1 project. The migrated legacy
  entry point is compiled and called; its modern adaptation is then compiled and exercised
  with modern and legacy clients.

## Limits and production checks

The deterministic agent policy exercises pagination and tool composition; it is not an LLM
quality benchmark. Before shipping, evaluate representative tasks in the actual target host,
checking outcomes against independent API/database evidence and inspecting discovery/recovery
traces. Protocol compatibility does not guarantee every host supports every capability.

HTTP auth fixtures verify resource-server behavior, not a full third-party OAuth flow. Test
protected-resource metadata, issuer discovery, PKCE, consent, refresh and revocation with the
chosen provider. Never pass client bearer tokens through to unrelated downstream services.
Use production key management, durable state, request/concurrency limits and rate controls.
Extensions such as tasks, skills and apps stay opt-in and require host-specific validation.

Sources: [MCP specification](https://modelcontextprotocol.io/specification/2026-07-28),
[authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization),
[Python SDK migration](https://py.sdk.modelcontextprotocol.io/migration/),
[TypeScript 2.4.0](https://github.com/modelcontextprotocol/typescript-sdk/releases/tag/v2.4.0).
