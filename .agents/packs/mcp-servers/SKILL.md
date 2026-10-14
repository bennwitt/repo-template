---
name: mcp-servers
description: "Write Python MCP servers with FastMCP 4 or the official mcp 2.x SDK (MCPServer): serving both the 2026-07-28 and handshake protocol eras, porting mcp.server.fastmcp code, mounting in FastAPI, Open WebUI clients, in-memory tests, Inspector checks, evaluation questions. Use when building, porting or testing an MCP server in Python."
---

# Writing MCP servers in Python

Two things moved at once in 2026, and most MCP code an agent writes from memory predates both:

- **The protocol.** Spec revision 2026-07-28 (the current one; `/specification/latest` redirects
  to it) drops the `initialize` handshake, sessions and every server-initiated request. Clients
  built before it still speak the handshake era, so a server serves both.
- **The libraries.** `mcp` 2.x renamed its bundled `FastMCP` to `MCPServer`; `import
  mcp.server.fastmcp` now raises `ModuleNotFoundError`. Standalone FastMCP 4 is built on `mcp` 2.x.

Facts below were checked against fastmcp 4.0.11, mcp 2.3.0, spec 2026-07-28 and MCP Inspector
2.9.0. Check the installed versions before relying on any of them. For FastAPI itself use the
`fastapi` skill, for Open WebUI's side the `openwebui` skill, for dependencies the `uv` skill.

## 1. Look before you change

- Find what is locked: `grep -A1 -E '^name = "(fastmcp|mcp)"' uv.lock`, and what pulls `mcp`
  in: `uv tree --invert --package mcp`. A dependency pinning `mcp<2` holds the whole environment
  on v1. langchain-mcp-adapters 0.3.2 does; its repository is archived, and LangChain moved MCP
  into the `langchain[mcp]` extra.
- Grep the imports. `from mcp.server.fastmcp` is v1 code (section 7); `from fastmcp` needs its
  major checked; `fastapi_mcp` is the tadata package (section 2).
- List the clients that will connect and their protocol era. Open WebUI 0.11.4 and 0.12.0 pin
  `mcp==1.27.2`, whose newest protocol version is 2025-11-25: it speaks the handshake era only,
  over Streamable HTTP only, and only admins can add servers.

## 2. Pick the library

| Situation | Use |
|---|---|
| Default: tools for agents, a FastAPI mount, auth providers, composing servers | FastMCP 4 (`fastmcp`, Apache-2.0) |
| Fewest dependencies, or code already on the official SDK | `mcp` 2.x `MCPServer` (MIT) |
| Exact hand-written schemas, custom JSON-RPC methods | `mcp` 2.x low-level `Server` |
| A quick look at an existing FastAPI app through MCP | `FastMCP.from_fastapi(app=app)`, as a prototype only |

- FastMCP is the default here because LangChain's `langchain[mcp]` extra already requires
  `fastmcp>=4.0.1,<5` (langchain 1.4.3), so one framework serves both server and client code.
- The low-level `Server` takes handlers as constructor arguments
  (`Server("x", on_list_tools=..., on_call_tool=...)`) and never validates arguments against the
  schema you advertise. An exception in `on_call_tool` becomes a JSON-RPC error, not a tool
  result: `-32603 Internal server error` on 2026-07-28, and code `0` with the raw exception text
  on handshake connections. Catch it and return `CallToolResult(is_error=True, ...)` for
  failures the model should see.
- Leave tadata's `fastapi-mcp` out. Its last release, 0.4.0 (2025-07-28), requires `mcp>=1.12.0`
  with no upper bound and crashes on mcp 2 (issue #321, open); issue #324 (open) reports
  unauthenticated HTTP access when `AuthConfig` is unset; the mcp 2 support PR #342 was closed
  unmerged. Mount a FastMCP server instead (section 6).
- Pin to the newest release at least 7 days old. On 2026-10-14 that was
  `uv add "fastmcp==4.0.11"` (2026-10-04) or `uv add "mcp==2.3.0"` (2026-10-02). For a newer
  one, read the upload dates in `https://pypi.org/pypi/fastmcp/json`
  (`releases.<version>[].upload_time_iso_8601`).
- FastMCP 4 needs Starlette 1.x, so FastAPI 0.133.0 or later, and pydantic 2.12 or later.

## 3. Serve both protocol eras

FastMCP 4 and `MCPServer` answer both eras from one server, and the client picks one. FastMCP
has no setting that restricts the versions a server offers. The Python `Client` (both
libraries) defaults to `mode="auto"` and lands on 2026-07-28 against your own server; the
Inspector defaults to legacy. Write every tool so it works on both:

- **User input arrives as tool arguments.** `ctx.elicit()` works only on handshake connections;
  on 2026-07-28 the call fails with "elicitation via server-initiated requests is unavailable on
  2026-07-28 connections". When a tool truly must ask mid-call: in FastMCP branch on
  `ctx.request_context.protocol_version`, return an `InputRequiredResult` (from `mcp.types`) on
  modern connections and read the answer from `ctx.input_responses` when the client calls again
  (<https://gofastmcp.com/servers/elicitation.md>); in `MCPServer` annotate a parameter with
  `Resolve(fn)` whose `fn` returns `Elicit(message, Model)`, which the SDK carries over either era.
- **Generation happens in your server.** FastMCP 4 removed `ctx.sample()`,
  `ctx.sample_step()` and `ctx.list_roots()`; Roots, Sampling and Logging are deprecated in the
  spec. Call your model provider directly, and take paths as tool arguments.
- **State lives in explicit handles.** On 2026-07-28 every request is fresh: `ctx.set_state`
  values do not survive to the next call and `Middleware.on_initialize` never runs. Return an id
  from one tool and accept it as an argument in the next. FastMCP's `SessionId` and
  `SessionProvider` (`fastmcp.server.sessions`) do this for you.
- `ctx.info()` and friends fail on neither era, but on 2026-07-28 the spec delivers the message
  only to a request that asks for a log level. The `MCPDeprecationWarning` they raise is the SDK
  flagging the deprecated capability and is harmless. Operator logs go to stderr or
  OpenTelemetry.
- Background tasks are now the `io.modelcontextprotocol/tasks` extension: in FastMCP,
  `fastmcp[tasks]` plus `mcp.add_extension(TasksExtension())` (`from fastmcp_tasks import
  TasksExtension`), or a server with a `task=True` tool refuses to start. Only modern
  connections get tasks; on handshake connections the tool runs synchronously.

## 4. Tools an agent can use well

- Build a few purpose-built tools, not one per REST endpoint. FastMCP's own docs report that
  models do significantly better with curated tools than with an auto-converted OpenAPI surface.
- Keep names short and snake_case. Open WebUI offers each tool to the model as
  `<server id>_<tool name>`, and the OpenAI API rejects tool names over 64 characters, so keep
  that under 64. Claude Code drops a tool whose `mcp__<server>__<tool>` name exceeds 128
  characters.
- The docstring is the description the model reads and the type hints are the schema, so say
  what the tool is for, what ids look like and what it returns.
- Return small results: page and filter on the server. Claude Code warns above 10,000 tokens of
  tool output and truncates at 25,000 by default (`MAX_MCP_OUTPUT_TOKENS`).
- Mark tools that only read: `@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))` with
  `ToolAnnotations` from `mcp.types` (the camelCase `readOnlyHint=` still constructs). It is a
  hint: the spec tells clients to treat annotations from untrusted servers as untrusted, so it
  never replaces a server-side check.
- Raise `ToolError("No order Z-9. Ids look like A-1.")` (FastMCP: `fastmcp.exceptions`;
  `MCPServer`: `mcp.server.mcpserver.exceptions`) for errors the model should act on. FastMCP
  sends any other exception's text to the client unless you create the server with
  `FastMCP(..., mask_error_details=True)`; `MCPServer` already hides it.
- A stdio server writes only MCP messages to stdout; send every log and `print` to stderr.

## 5. Serve over Streamable HTTP

- FastMCP: `mcp.run(transport="http")` (`"streamable-http"` is an alias) binds 127.0.0.1:8000
  and serves `/mcp`. `MCPServer`: `mcp.run("streamable-http")`. The SSE transport is deprecated
  in the spec; add it only for a client that needs nothing else.
- Inside a container bind `0.0.0.0` and publish the port on loopback (`docker-compose-patterns`).
- **Host and Origin checks** guard against DNS rebinding, and the spec requires servers to
  validate `Origin`. The libraries default differently:
  - `MCPServer` turns the check on only when `host` is localhost, its default: then any other
    Host gets a 421 ("Invalid Host header"). With `host="0.0.0.0"` and no `transport_security`
    there is no check at all. Pass
    `transport_security=TransportSecuritySettings(allowed_hosts=[...], allowed_origins=[...])`
    (from `mcp.server.transport_security`) whenever the server leaves localhost. Entries are
    `host:port`, with `:*` for any port (`"mcp.example.com:*"`). The list replaces the localhost
    entries, so add `"127.0.0.1:*"` back if local probes still need it.
  - FastMCP's `http_app()` and `run()` default to `host_origin_protection=False`: no check at
    all. `"auto"` checks only when the server is bound to loopback, so use it for a server on
    127.0.0.1. In a container or behind a hostname pass `True` with `allowed_hosts=[...]`
    (hostnames; localhost is always allowed) and `allowed_origins=[...]` for browser clients.
- `@mcp.custom_route("/health", methods=["GET"])` routes are never authenticated, by design.
  Keep them to health and readiness.
- More than one worker or replica: `stateless_http=True`. Sessions live in one process's memory,
  and FastMCP's docs report that most MCP clients do not keep the cookies sticky sessions need.
  The session is also the back-channel `ctx.elicit()` uses, so a stateless server cannot elicit
  from handshake clients either. A tool that returns `InputRequiredResult` needs every replica
  to share one key: `FastMCP(..., request_state_security=RequestStateSecurity(keys=[...]))`
  (from `mcp.server.request_state`), at least 32 random bytes read from the environment.
- Behind nginx, set `proxy_buffering off`, or streamed responses arrive only when the call ends.
- Tokens and keys come from the environment, never from source. FastMCP's auth providers
  (`JWTVerifier`, `RemoteAuthProvider`, `OAuthProxy`) are in its docs; a keyless server stays
  read-only.

## 6. Mount into FastAPI

```python
from fastapi import FastAPI
from fastmcp.utilities.lifespan import combine_lifespans

# mcp is your FastMCP server; app_lifespan is the app's own lifespan, if it has one
mcp_app = mcp.http_app(path="/mcp", host_origin_protection="auto")  # section 5
app = FastAPI(lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan))

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

app.mount("/", mcp_app)  # register it last
```

- **The host app owns the lifespan.** A mounted sub-app's lifespan never runs. Without
  `mcp_app.lifespan` the first MCP request fails with a 500 ("Task group is not initialized").
  `combine_lifespans` enters lifespans in order and exits them in reverse.
- **Mount at `/`, last.** Starlette matches routes in order and a mount at `/` takes every path,
  so routes added after it return 404. The common alternative, `http_app(path="/")` mounted at
  `/mcp`, serves `/mcp/` and answers `POST /mcp` with a 307 redirect, so every client given
  `/mcp` depends on following it. Either way, give clients the exact URL.
- With an OAuth-protected FastMCP mount, leave app-wide `CORSMiddleware` off: FastMCP already
  handles CORS on its OAuth routes, and a second layer can 404 the `.well-known` routes. Browser
  clients of a plain server need exact `allow_origins` and `allow_headers` naming `Content-Type`,
  `Authorization`, `Mcp-Protocol-Version`, `Mcp-Session-Id`, `Mcp-Method`, `Mcp-Name` and any
  `Mcp-Param-<Name>` a tool exposes (Starlette matches names exactly, so `Mcp-*` matches
  nothing), plus `expose_headers=["Mcp-Session-Id"]`.
- `MCPServer` instead: the host lifespan runs `async with mcp.session_manager.run(): yield`
  around `Mount("/", app=mcp.streamable_http_app())`, and `session_manager` exists only after
  `streamable_http_app()` has been called.

## 7. Port code that imports `mcp.server.fastmcp`

On mcp 2.x that import raises `ModuleNotFoundError: No module named 'mcp.server.fastmcp'. This
is mcp 2.x, where FastMCP was renamed to MCPServer...`. It usually means an unpinned `mcp`
crossed the major on a fresh lock, not that anyone chose to upgrade.

- Stopgap only: `uv add "mcp==1.30.0"` (the newest 1.x, 2026-09-07) restores the old module
  with no code change.
- Port to FastMCP 4 (usually the import, plus `host`/`port` moving to `run()`) or to
  `MCPServer` (a rename with more around it). [`references/migration.md`](references/migration.md)
  has both paths and the FastMCP 3 to 4 breaks; read it before porting.
- Either way the protocol types are snake_case now (`tool.input_schema`, `result.is_error`), and
  HTTP goes through `httpx2`: an `except httpx.ConnectError` around a FastMCP or SDK call still
  imports and type-checks but never matches.

## 8. Test in memory, on both eras

Pass the server object to `Client` and it connects in process: no port, no subprocess. Run
every tool test on both eras by parametrizing the fixture over `mode="auto"` (lands on
2026-07-28) and `mode="legacy"` (2025-11-25), and add one test that goes through the mounted
FastAPI app over HTTP in process. [`references/testing.md`](references/testing.md) has the
fixtures, which pass as written on fastmcp 4.0.11 with pytest-asyncio 1.4.0, and the two traps:
`httpx2.ASGITransport` buffers whole responses, and `run_asgi_lifespan` breaks with
`combine_lifespans`.

## 9. Check both eras with the Inspector

The Inspector connects in `legacy` by default and never probes, so a run that only uses the
default proves nothing about 2026-07-28 clients. Pin 2.9.0 (2026-09-30): 2.10.0 broke the plain
`npx` launch and its fix, 2.10.1, is less than 7 days old. It needs Node 22.19 or later.
`npm view @modelcontextprotocol/inspector time --json` lists newer releases and their dates.

```bash
npx -y @modelcontextprotocol/inspector@2.9.0 --cli \
  --server-url http://127.0.0.1:8000/mcp --transport http \
  --protocol-era legacy --method tools/list --strict
# repeat with --protocol-era modern, then call a tool on each era:
#   --method tools/call --tool-name order_status --tool-arg order_id=A-1
```

`--strict` exits 6 when a tool schema is not portable across clients. Other exit codes: 3 needs
auth, 4 unreachable, 5 the tool returned an error or does not exist. Without `--cli` the web UI
opens; set **Protocol Era** in the server's settings and repeat the checks.

## 10. Write evaluation questions

Tests prove the tools work; an evaluation shows whether a model with nothing but your server can
answer real questions with them. Write about ten question and answer pairs that are read-only,
independent, stable over time, need several tool calls each, and have one answer checkable by
string comparison. Run them through an agent that sees only this server. Format, criteria and
the run command are in [`references/evaluations.md`](references/evaluations.md).

## Check before you hand it back

```bash
uv run pytest                        # in-memory tests, both eras, plus the mounted-app test
uv run mypy src && uv run ruff check .
uv run uvicorn <package>.app:app --host 127.0.0.1 --port 8000   # serve on loopback
# then the Inspector checks in section 9, legacy and modern
```

A server with no FastAPI app serves itself from
`if __name__ == "__main__": mcp.run(transport="http")` (`uv run python -m <package>.server`).
Report which client eras you exercised and anything you could not run.

Primary docs: <https://gofastmcp.com/llms.txt> (FastMCP; any page with `.md` appended),
<https://py.sdk.modelcontextprotocol.io/llms.txt> (official SDK v2),
<https://modelcontextprotocol.io/specification/2026-07-28/changelog> (what the spec changed).
