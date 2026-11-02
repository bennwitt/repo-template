# Test MCP servers through clients

The canonical examples and exact dependency locks live in the standards repository's
[examples/mcp](https://github.com/bennwitt/repo-template/tree/main/examples/mcp). They are run
in CI; keep them as the source instead of copying a second set of snippets into this guide.
On a configured machine, `~/.agents` resolves into that checkout's `.agents` directory.

For the Python project, run `uv sync --locked --dev --python 3.12` and `uv run pytest` from
`examples/mcp/python`. For TypeScript run `npm ci --ignore-scripts`, `npm run build` and
`npm test` from `examples/mcp/typescript`, using Node 22.22.0. The pinned Inspector 2.12.0 needs
Node >=22.19. Real HTTP tests need loopback networking; a sandbox can prevent them running.

## What each boundary needs

- In memory: schema requiredness, enums and bounded arguments; structured output; missing
  resources; recoverable ToolError and redacted unexpected failures.
- Protocol compatibility: assert the actual negotiated revision using modern and legacy client
  modes. Default auto negotiation against a modern server exercises only the modern path.
- Stdio: spawn the installed package entry point, inspect discovery/results and close the client.
  Keep diagnostic output on stderr. A direct Python function call proves none of this.
- HTTP: use a real socket and exact endpoint path. Verify FastAPI's combined lifespan and cleanup,
  Host/Origin rejection, supported streaming behavior and multiple clients when applicable.
- Authorization: missing, malformed, expired, wrong-issuer/audience and insufficient-scope tokens;
  resource ownership independent of token validity. Read-only annotations do not enforce access.
- Cancellation: prove server work started, trigger a bounded client timeout, and assert backend
  work stops and resources close. Client rejection alone is insufficient.
- Agent workflow: follow pagination and compose tools, then compare results with independent
  state and verify unintended writes did not happen. Evaluate actual host/model usability
  separately from a deterministic tool-using policy.

Keep the project's existing asyncio test runner. The fixture uses pytest-asyncio; do not impose
it on projects using AnyIO. When a project requires an external OAuth provider, separately test
metadata discovery, PKCE, consent, refresh and revocation. Local JWT fixtures cannot establish
that provider's interoperability. Keep experimental capabilities opt-in and host-tested.
