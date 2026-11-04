# Global GitHub MCP and skills

Reviewed 2026-11-03 for the requested machine-wide GitHub integration.

## Selected integration

GitHub's hosted `https://api.githubcopilot.com/mcp/readonly` endpoint is global for Claude Code
and Codex. GitHub documents the `/readonly` suffix as restricting the exposed tools to reads.
The catalog permits one narrow authentication reference: `bearerTokenEnv` is exactly
`GITHUB_PERSONAL_ACCESS_TOKEN`, for this URL, server name and global scope. Arbitrary headers,
token values, credential URLs, other destinations and pack authentication remain rejected.

Claude receives an unexpanded Authorization variable reference; Codex receives
`bearer_token_env_var`. The generator never reads the credential. The managed Claude GitHub
plugin is disabled to avoid duplicates; manually changed client entries remain preserved.
The hosted service is updated by GitHub and cannot be pinned as a local package. Read-only tool
filtering is not a restriction on the token's authority outside that endpoint: use least-privilege
read permissions and the intended account. `gh` and MCP authentication are independent.

Sources: [GitHub hosted server](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md),
[GitHub's Codex configuration](https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-codex.md),
[OpenAI MCP configuration](https://developers.openai.com/codex/mcp),
[Claude environment expansion](https://code.claude.com/docs/en/mcp#environment-variable-expansion-in-mcpjson).

## Skill selection

| Skill | Decision and scope |
| --- | --- |
| `github-workflow` | New local MIT global skill: repository/account context, MCP versus CLI capabilities, template-aware PRs, exact-head merge checks and CI diagnosis. Reuses `pr` and `github-actions-hardening`. |
| `github-issues` | Local MIT adaptation of GitHub's skill at `edbecfa9099c4addae1f500cca1ac067204b30fd`, path `skills/github-issues`. Uses repository templates and metadata; MCP reads and explicitly requested CLI writes. |
| `github-actions-hardening`, `pr`, `code-review` | Retain existing global skills. |
| Upstream `gh-cli` | Search results still name it, but it is absent from the inspected source tree; do not install a stale search result. |
| Upstream `github-release` | Defer: prescriptive single-package release lifecycle overlaps existing delivery/PR guidance and is broader than the current request. |

The upstream issue skill names the retired `@modelcontextprotocol/server-github`, lists
`projects_write` among read tools, assumes writable MCP tools, and mandates its own templates.
The adaptation replaces those assumptions, uses body/payload files for safe CLI input, preserves
team conventions, and checks state before retrying uncertain writes. No upstream support scripts
or advanced API examples were copied. The existing pinned GitHub MIT license copy matches the
reviewed tree's `LICENSE` blob `89bc5e962c9944cdb050887062afdaaf89be504a`.

## Evidence and limits

A live authenticated initialize and tool-discovery request to the read-only endpoint succeeded,
negotiating protocol `2025-03-26` and returning 28 tools, all declaring `readOnlyHint: true`.
The user-provided `.env` credential stayed in memory and was sent only to the official endpoint;
redirects were rejected and no token value was stored or printed. No mutation tool was invoked.
This proves the supplied credential could connect at review time, not that every repository or
organization is accessible, and not that every exposed read tool has been exhaustively tested.

Regression tests cover the narrow credential-reference policy, secret-free client rendering,
preview/application/repeat behavior, preservation of foreign settings and machine-owned edits,
and replacement of the duplicate managed plugin. Static scans of both new skills reported no
findings. Behavioral guidance is source-reviewed; no comparative model benchmark is claimed.

The implementation passed 1,059 repository tests, Ruff lint/format checks, mypy, catalog
validation and self-check. Independent Standards and Spec reviews found no actionable issues.
An isolated test of the installed Claude CLI confirmed that `add-json` stores the literal
environment reference rather than a synthetic token value. Both new skills passed the skill
validator. Live client-session tool use still requires restarting with the credential environment.
