# Tool contracts and security

Design operations around user tasks. Give identifiers, required inputs, enum choices and
bounded output an explicit schema. Preserve signatures through wrappers. Test the schema
returned by tools/list, including requiredness and nested fields; a function's own test is
insufficient. Return continuation information when results are partial.

Use typed tool errors for recoverable failures; do not turn upstream failure into empty success.
Mask unexpected backend exceptions. Never log credentials or whole protocol payloads by default.
For stdio, all diagnostic output goes to stderr.

Annotations such as readOnlyHint describe intent; they do not authorize access. Enforce identity,
resource ownership and scopes server-side for every call. Reject cross-user resource identifiers
without leaking their existence. Bound payloads and concurrency and propagate cancellation.

For protected HTTP use the MCP authorization flow: protected-resource metadata, issuer validation,
PKCE where applicable, audience/resource binding and scope checks. Reject token passthrough;
use separately scoped credentials for downstream services. Host/Origin controls and CORS do not
replace authentication. Stdio obtains required credentials through the environment.

Test missing, malformed, expired, wrong-audience and insufficient-scope tokens, plus cross-user
access. JWT or synthetic-token fixtures do not prove an external OAuth provider's complete flow;
exercise discovery, consent and refresh against the chosen provider before shipping it.

Source: [authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization).
