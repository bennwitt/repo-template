# Setting up Moore's Figma space

## Once, by a Figma admin

1. **Seats.** Designers get Full seats. Developers get Dev seats: Dev Mode, Code Connect and the
   MCP server's daily allowance, with canvas writes only in their own drafts. Everyone else gets
   View or Collab seats, which allow 20 MCP calls a month.
2. **Folders.** In the team, create three top-level folders: `Sandbox`, `Dev` and `Prod`. Sandbox
   and Dev keep the team's access ("Anyone in the team can access").
3. **Limit Prod.** In Prod's share settings, limit it to "Only people added to Prod can access".
   Add the library maintainers with **can edit** and everyone else with **can view**. Add each new
   team member to Prod as a viewer.
4. **Library.** Put the design system file in Prod, named `Moore Design System` (a library takes
   its file's name). Publish it: Assets tab, Libraries icon, This file, **Publish**, with a
   description. Anyone who can view the file can then use the library.
5. **Code Connect.** Map the library to the React components with the `figma-implement-design`
   skill's `references/code-connect.md`. Professional allows one active library and one
   framework.
6. **Fonts.** Canvas writes can use only fonts Figma has. Montserrat and Zilla Slab are among
   Figma's Google fonts; Segoe UI, installed only on computers, isn't available to them.

## Once per person

1. **Pack.** Add the figma pack to the repository: `repo-template update . --pack figma` (with
   `--personal` in a repository others work in).
2. **Sign in.** In Claude Code, run `/mcp`, select `figma` and authenticate in the browser. In
   Codex, run `codex mcp login figma`. `FIGMA_TOKEN` doesn't sign this server in; it is for
   publishing Code Connect mappings.
3. **Writes, only for someone who writes to the canvas:**
   `repo-template globals --allow-write-mcp figma-write`, then `repo-template update .` in each
   repository with the pack, then sign in to `figma-write` the same way.
