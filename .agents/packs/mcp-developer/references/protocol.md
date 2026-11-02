# Protocol and transport selection

Current default: [MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28).
Requests carry version/capability metadata; modern requests are self-contained. Let the SDK
perform discovery and metadata handling rather than hand-building JSON-RPC lifecycle messages.
The initialize handshake and connection sessions belong to the legacy 2025-11-25 path.

Use stdio for local subprocess tools and Streamable HTTP for remote services. Streamable HTTP
can stream an individual response using SSE; this is different from the old standalone SSE
transport. Keep the latter only for a specifically identified legacy client.

Client capability support must be observed, not inferred. Modern elicitation is multi-round-trip
input, not a server-initiated request. Tasks, Skills over MCP and MCP Apps are opt-in extensions;
verify the host supports each before adopting it. Session-memory state is not durable state.
Use explicit handles and shared storage for multi-call workflows and multiple replicas.

Sources: [transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports),
[Python migration](https://py.sdk.modelcontextprotocol.io/migration/).
