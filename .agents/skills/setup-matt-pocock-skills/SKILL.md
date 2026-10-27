---
name: setup-matt-pocock-skills
description: "Configure a repository's Pocock workflows: issue tracker, triage labels and domain-document locations. This configures already installed skills; run when those workflows need missing repository conventions."
disable-model-invocation: true
---

# Configure Pocock workflows

This is repository configuration, not skill installation. Ordinary coding, tests and review of
a supplied local spec do not require it. Tracker-dependent workflows read the files below.

## Discover and resolve choices

Read existing `AGENTS.md`, `CLAUDE.md`, `docs/agents/`, glossary/ADR locations, Git remotes and
local issue conventions. Preserve established decisions and prior answers. A missing remote
does not prevent choosing local Markdown; adding a remote is outside this setup's scope.

Resolve only unsettled choices:

- **Issue tracker:** existing GitHub/GitLab repository, local Markdown, or a described external
  workflow. Read existing access configuration; do not change credentials or send content to
  a service just to establish the choice.
- **Triage labels:** use existing labels or the defaults `needs-triage`, `needs-info`,
  `ready-for-agent`, `ready-for-human`, `wontfix`. Include this file when triage is installed.
- **Domain layout:** keep existing paths. Otherwise one `GLOSSARY.md` and `docs/adr/` usually
  suffice; use multiple domain contexts only when the codebase needs them.

Use the accompanying tracker, triage and domain templates as starting points, preserving real
project details. Show unresolved choices with recommended defaults. Existing authorization for
setup covers the agreed local files; don't ask again for the same decisions.

## Write project configuration

Create or update `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md` when applicable,
and `docs/agents/domain.md`. These belong to the project; merge their existing content rather
than overwriting it. Templates are starting points, not instructions to invent remote addresses
or replace an existing tracker. Leave the "PRs as a request surface" flag off unless requested.

Put one concise `Agent skills` pointer block in `AGENTS.md` when it exists. Preserve `CLAUDE.md`
as `@AGENTS.md` when it is an import stub. If only a substantive `CLAUDE.md` exists, update its
existing block without creating a competing guide. With neither, create `AGENTS.md` for the
shared instructions and an import stub only when appropriate to the repository's conventions.

The block names the tracker and links the created files. Include a path only when the file
exists. Keep domain definitions in the glossary and architectural decisions in ADRs.
If legacy `CONTEXT.md` exists, inspect and propose a content-preserving migration separately;
don't rename or split project documents as a side effect of recording their location.

Tracker label creation is an external mutation. Record the desired vocabulary locally, then
create missing remote labels only when the user has authorized that operation; inspect existing
names and preserve their descriptions/colors. Local Markdown needs no remote labels.

## Verify

Read back the configuration and resolve every pointer. Check that issue operations route to
the chosen tracker, domain paths match the project, and `CLAUDE.md` still imports the authoritative
guide when it did before. A repeat run with the same choices makes no changes. Report local
configuration completed and any remote setup that remains, without claiming credentials work
unless a relevant read-only check verified them.

Adapted from Matt Pocock's setup skill (MIT). Its tracker/domain templates are retained in this
folder; pinned provenance is recorded in the standards catalog.
