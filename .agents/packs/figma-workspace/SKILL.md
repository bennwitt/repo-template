---
name: figma-workspace
description: "Moore's Figma space: the Sandbox, Dev and Prod folders, who edits each, where agents may write, how the design system library is released, and Figma links, seats and sign-in. Use before reading or writing a Figma file, when filing or promoting design work, or when setting up the space."
license: MIT
compatibility: "Moore's Figma team on the Professional plan, and the figma pack's servers: figma (read-only) and, on a machine granted it, figma-write."
---

# Moore's Figma space

Moore's Figma is one team on the Professional plan. Its three top-level folders are
**environments**: work starts in Sandbox, matures in Dev and lands in Prod, and Prod is the
source of truth developers build from.

| Folder | Holds | Who edits | Agent writes |
|---|---|---|---|
| **Sandbox** | Experiments, training files, copies of files for trying a change, and anything an agent generates | everyone on the team | yes: this is where they go |
| **Dev** | Work in progress, a file per product or feature. A section marked **Ready for dev** is a build request | designers | only when the file's owner asks |
| **Prod** | The **Moore Design System** library file, and the approved designs of what is live | library maintainers | none |

Inside each, nest folders by product or client; a nested folder inherits its parent's access.

## What the plan decides

- **No branching.** A library change is made in the library file itself and reaches other files
  only when a maintainer **publishes** it: publishing is the release. Try a risky change on a
  copy in Sandbox first.
- **Access is set on top-level folders only**, which is why Sandbox, Dev and Prod are top-level.
  Prod is limited to the people added to it: maintainers can edit, everyone else can view.
- **One Code Connect library and one framework:** the Prod library, mapped to our React code.
- **Up to 10 modes per variable collection**, such as light and dark.

## Point at a file

The remote server works from links, not from what is selected in Figma. Ask for a link when you
have none: in Figma, right-click a layer and choose **Copy link to selection**, or copy the
browser address for a whole file. A design link looks like
`https://www.figma.com/design/<fileKey>/<name>?node-id=12-34`; node `12-34` in the URL is `12:34`
in the tools. Note which folder the file is in before you change anything.

## Read and write

- **Read** with the `figma` server, anywhere the person can view. Calls are rationed per person:
  a Dev or Full seat gets 200 a day and 10 a minute, View and Collab seats 20 a month. Take an
  outline (`get_metadata`) first, then fetch only the parts you need, once each.
- **Write** only with `figma-write`, which exists only on a machine granted it; Claude Code asks
  before each write. Write in Sandbox or the person's drafts, in Dev only when the file's owner
  asks, and never in Prod. Figma enforces edit access anyway, and a Dev seat writes only to
  drafts. Canvas writing is in beta: before a large change, duplicate the file into Sandbox and
  work on the copy.
- **Brand:** check frames against Moore's style guide with the moore-ux plugin's
  `moore-figma-adherence` skill when it is installed.

## Promote work

1. **Sandbox to Dev:** when an experiment is worth keeping, move its frames into the product's Dev
   file, or move the file into Dev.
2. **Dev to code:** mark the section **Ready for dev**; developers build from it with the
   `figma-implement-design` skill.
3. **Dev to Prod:** when the design ships, a maintainer moves the approved file or pages into Prod.
4. **Library release:** a maintainer makes the change in the library file and publishes it
   (Assets tab, Libraries icon, **Publish**) with a description of what changed. Figma shows that
   description to everyone accepting the update and keeps it in version history. **Hide when
   publishing** keeps unfinished assets out. Then update the Code Connect mappings of the changed
   components.

## Set up the space

The one-time steps for a Figma admin, and the ones each person does once:
[references/setup.md](references/setup.md).
