---
name: python-mcp-server-generator
description: "Create Python MCP servers with official SDK v2: preserve existing uv/src layouts, add typed tools and structured errors, and test modern and required legacy clients over real transports. Use for new servers or exposing project functions as MCP tools; application migrations require explicit scope."
license: MIT
---

# Python MCP server generator

Adapted from github/awesome-copilot (MIT); changed project setup, version pinning and test
coverage. Original provenance and license are retained in the standards catalog.

1. Inspect the repository's manifest, lockfile, imports and target clients. In an existing uv
   project keep its package and tests layout; skip `uv init`. For a new project use the project's
   scaffold conventions. Use a package module in `src/<package>/`, not an unrelated root script.
2. New servers use `mcp==2.3.0` (`mcp[cli]==2.3.0` only when the CLI is needed). Add it with uv,
   commit the lockfile, and inspect dependency constraints. An SDK v1 dependency is a migration
   decision, not permission to silently force SDK v2.
3. Follow the canonical, executable
   [SDK example](https://github.com/bennwitt/repo-template/blob/main/examples/mcp/python/src/mcp_example/sdk_server.py).
   Import `MCPServer` from `mcp.server`, and `ToolError` from
   `mcp.server.mcpserver.exceptions`. Set a server version; give tools typed inputs and documented
   outputs. Return typed models for structured results. Keep output bounded and validate ownership.
4. Test through `mcp.Client(server)` and real transport clients. Cover discovery, schema requiredness,
   successful structured output, invalid inputs and tool errors. Run modern and legacy cases only
   for supported clients. The checked fixture uses pytest-asyncio; retain an existing test runner
   rather than imposing a second asyncio plugin.
5. Local subprocess servers use stdio and log only to stderr. Configure clients with an absolute
   project directory and `uv run python -m <package>.<module>`. Remote servers follow
   [streamable-http.md](references/streamable-http.md).
6. Run the project checks, then Inspector 2.12.0 with Node >=22.19 where an interactive review is
   useful. Readiness requires real client/transport tests, not merely successful import or Inspector startup.

SDK v2 models use snake_case (`structured_content`, `is_error`). For modern protocol input
requests use the SDK's `Resolve`/`Elicit` facilities, not legacy session callbacks. Read the
[SDK migration guide](https://py.sdk.modelcontextprotocol.io/migration/) for an explicitly requested port.
