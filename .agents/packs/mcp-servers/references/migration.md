# Porting MCP server code to mcp 2.x

Checked against fastmcp 4.0.11 and mcp 2.3.0. The full guides, with every edge case:
FastMCP's <https://gofastmcp.com/getting-started/upgrading/from-mcp-sdk-v1.md> and
<https://gofastmcp.com/getting-started/upgrading/from-fastmcp-3.md>, and the SDK's
<https://py.sdk.modelcontextprotocol.io/v2/migration/>.

## Which code you have

| First lines of the server | What it is | Path |
|---|---|---|
| `from mcp.server.fastmcp import FastMCP` | FastMCP 1.0, bundled in `mcp` v1, even when a `fastmcp` 3.x package is also installed | A or B |
| `from fastmcp import FastMCP` with `fastmcp` 3.x locked | Standalone FastMCP | C (on 2.x, first read <https://gofastmcp.com/getting-started/upgrading/from-fastmcp-2.md>) |
| `from mcp.server.lowlevel import Server` with `@server.list_tools()` decorators | The v1 low-level server, rebuilt in v2 | The SDK guide's "Lowlevel Server" section |

Path A is usually the smaller change, because FastMCP 1.0 was contributed from early FastMCP and
standalone FastMCP kept the same high-level API. Take path B when the project should depend on
the official SDK alone. Run the tests from `testing.md` on both eras after either.

## A: FastMCP 1.0 to FastMCP 4

`uv add "fastmcp==4.0.11"` (or the newest release at least 7 days old). It brings `mcp>=2,<3`.

| v1 | FastMCP 4 |
|---|---|
| `from mcp.server.fastmcp import FastMCP` | `from fastmcp import FastMCP` |
| `from mcp.server.fastmcp import Context` | `from fastmcp import Context` |
| `from mcp.server.fastmcp import Image` | `from fastmcp.utilities.types import Image` |
| `mcp.types.TextContent(type="text", text=str(x))` returned from a tool | return `x` |
| `mcp.types.PromptMessage(...)`, or a prompt returning a `{"role", "content"}` dict | `from fastmcp.prompts import Message`, or return a `str` |
| `from mcp.server.stdio import stdio_server` boilerplate | `mcp.run()` |

**Constructor arguments that moved.** `host`, `port`, `log_level`, `debug`, `sse_path`,
`message_path`, `streamable_http_path`, `json_response` and `stateless_http` now go to
`mcp.run(transport="http", ...)`, `mcp.http_app(...)` or a `FASTMCP_*` environment variable;
each raises a `TypeError` naming its new home, so running the server finds them. These fail
with only a generic "unexpected keyword argument":

| v1 `FastMCP(...)` | FastMCP 4 |
|---|---|
| `event_store=` | `mcp.http_app(event_store=...)`. Dropping it silently turns off stream resumability. |
| `mount_path=` | `mcp.http_app(path=...)` |
| `transport=` | `mcp.run(transport=...)` |
| `transport_security=` | `host_origin_protection=`, `allowed_hosts=`, `allowed_origins=` on `http_app()` |
| `warn_on_duplicate_tools=` and the resource and prompt variants | one `on_duplicate=` |
| `dependencies=[...]` | a `fastmcp.json` file |
| `token_verifier=`, `auth_server_provider=`, `auth=AuthSettings(...)` | one `auth=` provider: `JWTVerifier`, `RemoteAuthProvider`, `OAuthProxy` or a named one, from `fastmcp.server.auth` |

`name`, `instructions`, `website_url`, `icons`, `tools` and `lifespan` carry over unchanged.

**Context calls that compile and then fail.**

| v1 | FastMCP 4 |
|---|---|
| `ctx.log(level, data)` | `ctx.log(message, level=...)` |
| `ctx.info(data)` with a non-string | `ctx.info("text")`: a `str` message |
| `ctx.elicit(message, schema=Model)` | `ctx.elicit(message, response_type=Model)`, handshake era only (SKILL.md section 3) |
| iterating `ctx.read_resource(uri)` | `(await ctx.read_resource(uri)).contents` |

Decorators now return your original function, so code reading `.name` off a decorated tool needs
`await mcp.get_tool("name")` instead. Check that every component came across with
`fastmcp inspect <path to server.py>`.

## B: FastMCP 1.0 to the SDK's MCPServer

`uv add "mcp==2.3.0"` (or the newest release at least 7 days old).

- `from mcp.server.mcpserver import MCPServer, Context` (`MCPServer` is also exported from
  `mcp.server`). Everything under `mcp.server.fastmcp.*` moved to `mcp.server.mcpserver.*` with
  the same structure. `ToolError`, `ResourceError` and `MCPServerError` (formerly
  `FastMCPError`) come from `mcp.server.mcpserver.exceptions`; `Message`, `UserMessage` and
  `AssistantMessage` from `mcp.server.mcpserver.prompts.base`.
- Decorators keep their parentheses and arguments: `@mcp.tool()`, `@mcp.resource()`,
  `@mcp.prompt()`.
- `ctx.fastmcp` is `ctx.mcp_server`. `get_context()` is gone: declare a `ctx: Context`
  parameter.
- Transport arguments moved from the constructor to `run()` and the app methods, and
  `mount_path` was removed: `MCPServer.__init__() got an unexpected keyword argument 'port'`.
- `MCP_*` environment variables and `.env` files are no longer read; read the environment
  yourself and pass values to the constructor.
- A sync `def` handler now runs on a worker thread, so `asyncio.get_running_loop()` inside one
  raises `RuntimeError`. Make it `async def` if it needs the loop.
- Context logging takes `data` (any JSON value) instead of `message`, and `extra` is gone. The
  helpers are deprecated (SEP-2577); log with the `logging` module instead.
- The default server name changed from `FastMCP` to `mcp-server`: pass a name.
- Streamable HTTP request bodies are capped at 4 MiB (`max_request_body_size`).

## Both paths

- Protocol types live in `mcp-types`, re-exported as `mcp.types`, and every Python attribute is
  snake_case: `input_schema`, `is_error`, `mime_type`, `next_cursor`, `structured_content`. The
  JSON on the wire keeps its camelCase. FastMCP bridges the old reads with a warning; set
  `FASTMCP_MCP_CAMELCASE_COMPAT=false` in CI to turn each one into an `AttributeError`.
- `McpError` is `MCPError` (`from mcp import MCPError`), built as `MCPError(code, message)`
  rather than around an `ErrorData`.
- `httpx` is replaced by `httpx2` throughout. Grep for `except httpx.` around MCP calls and for
  custom `httpx.AsyncClient` or `httpx.Auth` objects handed to a transport; the fix is the
  import, since `httpx2` keeps the same API and exception names. FastMCP's HTTP calls now verify
  TLS against the operating system's trust store instead of certifi.
- Client code: `streamablehttp_client` was removed (use `streamable_http_client`, or the
  first-class `Client(url)`), and `Client` defaults to `mode="auto"`, so servers see a
  `server/discover` probe first.
- A missing resource now returns `-32602`, not `-32002`.

## C: FastMCP 3 to FastMCP 4

Most servers upgrade untouched. Look for these:

- `import_server(sub)` is gone. `mount(sub)` replaces it but is a live composition that runs the
  child's lifespan and middleware, where `import_server` took a static copy.
  `mount(prefix=...)` is `mount(namespace=...)`; `FastMCP.as_proxy(sub)` is
  `create_proxy(sub)` from `fastmcp.server`.
- `ctx.sample()`, `ctx.sample_step()`, `ctx.list_roots()` and `FastMCP(sampling_handler=...)`
  are removed. FastMCP's guide says a server whose whole point is borrowing the caller's model
  should stay on 3.x.
- `ctx.elicit()` requires `response_type` and raises on 2026-07-28 connections.
- Tool `serializer=` (return a `ToolResult`) and `exclude_args=` (give the parameter a
  `Depends(factory)` default, from `fastmcp.dependencies`) are removed, as is
  `StreamableHttpTransport(sse_read_timeout=)`.
- Moved imports: `fastmcp.server.proxy` to `fastmcp.server.providers.proxy`,
  `fastmcp.server.openapi` to an `OpenAPIProvider` from `fastmcp.server.providers.openapi`, and
  `Tool`/`Resource`/`Prompt` from `fastmcp.tools`, `fastmcp.resources`, `fastmcp.prompts`.
- `task=True` needs `fastmcp[tasks]` and `mcp.add_extension(TasksExtension())`, and is now
  tools only.
- Templated resources reject `..` segments and absolute paths in their parameters before your
  handler runs; exempt a parameter with `ResourceSecurity(exempt_params={...})`.
- Middleware `on_message` now sees every message, notifications and unroutable requests
  included.
- An `OAuthProxy` server whose `issuer_url` differs from its `base_url` forces every client to
  re-authorize once.
