# MCP development evaluation — 2026-11-02

## Decision

Use MCP 2026-07-28 for new development and explicit 2025-11-25 compatibility tests where clients
require it. Application dependency migrations remain separate from skill installation. The
reviewed pins and publication timestamps are in [the baseline](../../.agents/mcp-development.json).
FastMCP 4.1.5 and Inspector 2.13 were newer but inside the seven-day cooldown at review time.

## Source and skill decisions

| Skill | Decision |
| --- | --- |
| mcp-developer | Keep its name, replace obsolete protocol and SDK examples with a maintained MIT derivation. Upstream still claimed 2024-11-05 was current and mixed unbounded installation with v1 imports. |
| mcp-servers | Keep local Python integration expertise; refresh FastMCP/Inspector guidance and link executable fixtures. |
| python-mcp-server-generator | Maintain as an MIT derivation so the body respects existing src-layout projects, pins and tests, not merely a frontmatter override. |
| fastmcp-server | Vendor the official PrefectHQ/fastmcp authoring skill unchanged at the recorded commit. |
| mcp-typescript-sdk-upgrade-to-v2 | Adapt the official guide: retain references, pin the codemod, require migration scope, and preserve the distinction between SDK and protocol upgrades. |

Final static scans of all five MCP skills reported no findings. Manual review found no load-time
commands, permission changes, credential collection or hidden execution. The migration command
is an explicit task step, now pinned and scoped. Source URLs are official documentation/GitHub
links. References and license files remain included; exact commits/tree hashes are in the catalog.

FastMCP's skill is Apache-2.0. The TypeScript repository LICENSE distinguishes documentation
(CC-BY-4.0) from code (Apache-2.0 with legacy MIT portions); the migration guide's adaptation
records CC-BY-4.0, authorship, source and modifications. Existing derived skills retain MIT
attribution. [Third-party notices](../../THIRD_PARTY_NOTICES.md) enumerate the recorded sources.

## Validation and limits

The [locked fixtures](../../examples/mcp/README.md) exercise both protocol eras through real
stdio and loopback HTTP connections. Python additionally checks official SDK calls, FastAPI
lifespan, pagination, redacted failures, JWT validation and owner isolation. TypeScript checks
factory-based entry points, scoped bearer middleware, cancellation and the official pinned
codemod on a disposable project. The generated code is compiled and called through stdio,
then adapted to the modern entry point, compiled again and exercised in both protocol eras. A deterministic agent policy composes tool calls and compares
its answer with independent fixture state; this is not a model-quality benchmark.

The fixtures use synthetic data and local credentials. They do not certify external OAuth
provider discovery/PKCE/consent/refresh, production deployment configuration, every host's
capabilities, or experimental extensions. Those need the relevant project's integration tests.

Catalog tests cover provenance and license integrity; development pin tests cover cooldowns,
missing packages and network failures. Fixture-lock assertions detect divergence from the
baseline. Weekly upstream reporting detects available development updates without installing them.

Local validation: 1,028 repository tests, 12 Python fixture tests and 7 TypeScript fixture tests
pass; TypeScript compilation, Ruff and mypy pass. Full, packs-only and personal adoption
smoke checks preserve individual selections. Independent standards and requirements reviews
reported no remaining findings after correcting stale pins, pinning CI tooling and adding
execution of the codemod output.

## Primary sources

- [MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
- [Transport definitions](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)
- [Authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- [Python SDK migration](https://py.sdk.modelcontextprotocol.io/migration/)
- [Python releases](https://pypi.org/pypi/mcp/json)
- [FastMCP releases](https://pypi.org/pypi/fastmcp/json)
- [Official FastMCP skill](https://github.com/PrefectHQ/fastmcp/tree/901575873111515457755df6872d7b0ccdf9407b/skills/fastmcp-server)
- [TypeScript SDK 2.4.0](https://github.com/modelcontextprotocol/typescript-sdk/releases/tag/v2.4.0)
- [Official TypeScript migration skill](https://github.com/modelcontextprotocol/typescript-sdk/tree/1e608caeb5130b2ad0fa067c84b26a038c1c6e36/skills/mcp-typescript-sdk-upgrade-to-v2)
