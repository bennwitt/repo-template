---
name: figma-implement-design
description: "Build or update UI from a Figma frame with the figma pack's read-only server: outline, design context, screenshot, variables mapped to project tokens, existing components through Code Connect, assets, then a visual comparison. Use when implementing code from a Figma link, or setting up or publishing Code Connect."
license: MIT
compatibility: "The figma pack's figma server (Figma's remote MCP server, signed in per client). Publishing Code Connect needs Node 18 or later, a Dev or Full seat and FIGMA_TOKEN."
---

# Implement a Figma design

The `figma` server reads; you write the code. The code it returns is a **reference**, React and
Tailwind by default: translate it into this repository's components, tokens and conventions
rather than pasting it.

## Before you start

- If the `figma` tools fail to authenticate, the person signs in once: in Claude Code, `/mcp`,
  select `figma`, authenticate; in Codex, `codex mcp login figma`. A `FIGMA_TOKEN` in the
  environment doesn't sign this server in. With no `figma` server at all, the repository lacks
  the figma pack: `repo-template update . --pack figma`.
- Get a link to the frame (the `figma-workspace` skill says how). Build from a **Ready for dev**
  section in Dev or from Prod; a Sandbox frame is an experiment, so confirm before building it.
- Calls are rationed (a Dev or Full seat gets 200 a day, 10 a minute): fetch each node once and
  reuse what came back.

## Steps

1. **Locate.** Take the file key and node id from the link (`node-id=12-34` is `12:34`). With
   only a file link, `get_metadata` without a node id lists the pages; choose with the person.
   Done when you have a node id for each frame to build.
2. **Outline.** `get_metadata` on the frame returns its layers' ids, names, types and sizes.
   Done when the frame is split into parts small enough to fetch one at a time; a large frame in
   one `get_design_context` call returns too much.
3. **Context.** `get_design_context` on each part, with `clientFrameworks` set to the Code
   Connect label (`React`) and a prompt naming this repository's framework and component folder,
   such as "use components from src/components/ui". Instances mapped with Code Connect come back
   marked `CodeConnectSnippet`.
4. **See.** `get_screenshot` of the whole frame: the target for step 9.
5. **Tokens.** `get_variable_defs` lists the variables and styles the frame uses. Map each to
   this repository's tokens (the Tailwind theme, CSS custom properties).
   Done when every variable maps to a token or is on a list of missing tokens; a raw value never
   stands in for a variable.
6. **Components.** `get_code_connect_map` gives each mapped instance's code component, source
   path and snippet: import that component. For an unmapped instance, look in the repository's
   component folder and `search_design_system` before writing a new component.
   Done when every mapped instance uses its component and each new component covers something
   nothing existing does.
7. **Assets.** `download_assets` (up to 20 nodes a call) returns temporary URLs: save the files
   into the repository's asset folder straight away, SVG for icons. A screenshot is for looking,
   never for shipping.
8. **Build** the UI in the repository's stack.
9. **Compare.** Render the page at the frame's width, screenshot it with the repository's
   browser pack (playwright or stagehand), and compare it with step 4: layout, spacing, type,
   color, states.
   Done when the render matches, or each remaining difference is listed with its reason.

## Report

The link you built from, the files changed, the missing tokens, any new component, and the
differences left from step 9.

## Code Connect

Code Connect maps the library's components to this repository's code, which is what step 6
finds. To set it up or publish mappings, read
[references/code-connect.md](references/code-connect.md).
