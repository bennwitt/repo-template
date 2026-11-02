---
name: mcp-developer
description: "Design, build and debug MCP clients and servers in Python or TypeScript. Select version-matched SDKs, modern or legacy protocol entry points, transports, schemas, authorization and integration tests. Use for cross-language MCP development; SDK migrations require an explicit migration task."
license: MIT
---

# MCP development

Adapted from Jeffallan/claude-skills (MIT); provenance and license are recorded in the standards catalog.

## Choose a compatible implementation

1. Read the package manifest, lockfile, imports and actual client versions. Preserve existing
   dependency constraints unless upgrading is part of the task. A skill installation does not
   authorize an application migration.
2. For new work target MCP **2026-07-28**. Identify any required **2025-11-25** clients and test
   both; SDK version alone does not prove protocol support.
3. Use the tested baseline in the standards repository's `.agents/mcp-development.json`:
   Python `mcp==2.3.0`, FastMCP `4.1.4`; TypeScript server/client/core `2.4.0`, node adapter
   `2.1.2`; Inspector `2.12.0` (Node >=22.19). These are reviewed pins, not instructions to
   update an existing application. Newer releases need seven days and compatibility tests.
4. Follow the relevant reference, then validate the public client-visible contract.

| Work | Read |
| --- | --- |
| Protocol and transport decisions | [protocol.md](references/protocol.md) |
| Python clients or servers | [python-sdk.md](references/python-sdk.md); `mcp-servers` and `fastmcp-server` skills |
| TypeScript clients or servers | [typescript-sdk.md](references/typescript-sdk.md) |
| Tool contracts, errors and security | [tools.md](references/tools.md) |
| Resources and prompts | [resources.md](references/resources.md) |
| Requested TypeScript v1 migration | `mcp-typescript-sdk-upgrade-to-v2` skill |

For executable fixtures and their locks, use the standards repository's
[examples/mcp](https://github.com/bennwitt/repo-template/tree/main/examples/mcp).
Run tests in their own project directories. Never run a recursive formatter over installed
skill symlinks; format only files owned by the project being changed.

## Completion

Verify discovery, schema requiredness, structured results and failures through a real client.
Exercise the actual transport, auth boundaries, supported protocol eras, timeout/cancellation
and cleanup. For agent usability, verify the requested outcome against independent state;
a plausible final response alone is not evidence. Report what was and was not exercised.
