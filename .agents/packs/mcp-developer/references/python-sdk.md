# Python SDK selection

Use standalone FastMCP 4 for application facilities, or the official `mcp` 2.x SDK for a
smaller dependency surface. `from fastmcp import FastMCP` and `from mcp.server import MCPServer`
are different APIs. `mcp.server.fastmcp` is a legacy SDK v1 import and fails with SDK v2.

Use `uv` in this baseline; retain the project's `src/` and `tests/` layout. Read `mcp-servers`
for FastAPI lifespans, host/origin protection and migration. Use `fastmcp-server` for authoring
and version-matched documentation, or `python-mcp-server-generator` for an official-SDK server.

Both libraries provide an in-memory `Client(server)`. Test `mode="auto"` and `mode="legacy"`
when both eras are required; also exercise a real stdio subprocess and HTTP socket. SDK v2
protocol models use snake_case fields such as `structured_content` and `is_error`. FastMCP's
client additionally exposes parsed `.data`. Treat these as version-specific client APIs.

For SDK v1 applications, keep a bounded v1 constraint until an explicit migration. Do not
combine `pip install mcp` without a bound with an SDK v1 example. HTTP exceptions in v2 use
`httpx2`; old `httpx` exception handlers do not catch them.

Runnable examples: [Python fixture](https://github.com/bennwitt/repo-template/tree/main/examples/mcp/python).
Official APIs: [Python SDK](https://py.sdk.modelcontextprotocol.io/), [FastMCP](https://gofastmcp.com/llms.txt).
