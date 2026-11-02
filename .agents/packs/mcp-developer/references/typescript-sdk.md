# TypeScript SDK v2

The legacy `@modelcontextprotocol/sdk` package remains a v1 compatibility choice. For new
modern-protocol work use `@modelcontextprotocol/server`, `/client`, `/core` 2.4.0 and the
separately versioned `@modelcontextprotocol/node` 2.1.2 when running Node HTTP. Use the project's
package manager; pin exact reviewed versions and commit its lockfile. Inspector 2.12 requires
Node >=22.19; the fixture tests Node 22.22.0.

Import `McpServer` and `createMcpHandler` from `@modelcontextprotocol/server`, `serveStdio` from
`@modelcontextprotocol/server/stdio`, and `toNodeHandler` from `@modelcontextprotocol/node`.
Register schemas with `registerTool` and `z.object(...)`; return `content` plus `structuredContent`.

Build a server factory receiving `McpRequestContext`. `serveStdio(factory)` and
`createMcpHandler(factory)` support modern requests and stateless legacy fallback. Keeping
`server.connect(new StdioServerTransport())` after a package upgrade still serves legacy only.
For legacy session-dependent capabilities, use the documented explicit legacy transport route.

Clients import `Client` and `StreamableHTTPClientTransport` from `/client`, and
`StdioClientTransport` from `/client/stdio`. Configure `versionNegotiation: {mode: 'auto'}` or
`'legacy'`; assert `getNegotiatedProtocolVersion()`. `callTool(request, options)` no longer takes
a result-schema argument. Validate structured outputs before treating them as application data.

`createMcpHandler` provides no Host/Origin enforcement by itself. Wrap its fetch handler with
`hostHeaderValidationResponse` and `originValidationResponse`; use `requireBearerAuth` for a
protected endpoint and pass verified authInfo to the handler. Tools authorize each resource
against that identity. Propagate `ctx.mcpReq.signal` into backend I/O and test actual cleanup.

Runnable, typed [fixture](https://github.com/bennwitt/repo-template/tree/main/examples/mcp/typescript).
Sources: [v2.4.0](https://github.com/modelcontextprotocol/typescript-sdk/releases/tag/v2.4.0),
[modern entry points](https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28.md).
