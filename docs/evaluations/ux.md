# UX pack admission and use

Reviewed 2026-11-19 for task-oriented web interfaces, initially ZLlama's model manager.
The application stack and running inference sessions are outside this catalog change.

## Selection

The optional `ux` pack combines the existing `frontend-design` and
`web-interface-guidelines` skills with two additions:

| Skill | Source revision | License | Role |
| --- | --- | --- | --- |
| UI UX Pro Max | [2de1134dc4d1](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/2de1134dc4d1cfe112934611ae5803ae17a1bd7e/.claude/skills/ui-ux-pro-max) | MIT | Local searches for interaction, accessibility, layout and visual-system guidance |
| Impeccable | [b49177d32788](https://github.com/pbakaus/impeccable/tree/b49177d32788f2dc585c42831d845dacf1ebed2c/.agents/skills/impeccable) | Apache-2.0 | Shape, critique and refine flows, hierarchy, copy and visual design |

Both are copied through the catalog updater with immutable commits, tree/blob verification,
license copies and scanner evidence. Descriptions are shortened through the existing frontmatter
override mechanism; upstream bodies and supporting resources are retained. Updates and additions
from these sources require review. Existing frontend packs retain their membership; this pack is
an explicit project selection, and each skill is also available individually.

Choose one workflow for the current question. A narrow usability fix does not require running
all four skills. Impeccable's Operate mode fits management interfaces: clarity, consistency and
task completion take precedence over expressive decoration. Use UI UX Pro Max for focused
queries, validate the returned pattern against the actual product, and preserve established
frameworks. Plain HTML/CSS is not an instruction to install Tailwind or React.

## Admission findings and boundaries

The installed skill scanner reported 19 high findings for UI UX Pro Max, all the presence of
bundled `scripts/tests/test_*.py` files. These remain outside the standard project's configured
`tests/` discovery path. They are upstream test resources, not plugin hooks. Some require files
from the full upstream repository, so running the complete bundled suite from the isolated skill
folder is unsupported. Catalog admission does not claim that upstream's full suite passed.
The runtime uses Python's standard library; search reads bundled CSV/JSON data. Persist/preview
options explicitly write generated artifacts; previews may reference Google Fonts. Use an explicit
project output directory for persistence and preserve existing design decisions.

The scanner reported three high findings for Impeccable: `RegExp.exec` calls in
`scripts/live-browser.js` (lines 8767 and 8830) and the bundled screenshot library. These parse CSS
URLs, colors and styles; they are not JavaScript code evaluation. The allowance records this
specific interpretation, not a blanket approval of future executable changes.

Impeccable also contains a shell/Windows launcher and browser scripts. The launcher pins engine
0.1.27 and verifies downloaded binaries against bundled SHA-256 values. It also supports
operator-selected local binaries. Installing the pack installs neither the engine nor the native
plugin, hooks, browser extension or browser server. Invoking the launcher may download an engine
into the user's cache. Use the skill's documented direct-context fallback if unavailable; invoke
optional installation, hooks, live browser tooling and other mutations only within the user's
actual task and existing tool/permission boundaries. No runtime engine or browser scripts were
executed for catalog admission. This was a scoped source/packaging review, not a full engine audit.

The scanner does not parse all CSV/JSON data or bundled tests. Treat returned guidance and example
code as recommendations, not instructions overriding the user or repository. Verify technical
claims against the project's actual versions when implementing them.

## Portable invocation

UI UX Pro Max's upstream examples assume `CLAUDE_PLUGIN_ROOT`. repo-template installs skill
folders, not that plugin. Resolve the selected skill's real directory, then use the project's
Python runner and the absolute script path. For example from an adopted Python repository:

```bash
uv run python .agents/skills/ui-ux-pro-max/scripts/search.py "keyboard focus modal" --domain ux
```

Search needs no network or third-party Python dependency. Read the skill's query contract and
verify the returned issue fits the requested outcome. Use existing PRODUCT.md/DESIGN.md and
rendered UI evidence when shaping or critiquing an existing application; missing design documents
do not authorize a redesign.

## Verification

Catalog and project-link regression checks exercise the real pack, supporting-resource access,
individual-selection preservation, and a local search from outside the skill directory. Existing
repo-template tests cover hashes, licenses, catalog generation, profiles and conflict handling.
Validation results and distribution targets are recorded in the task handoff after execution.
No model operations or application deployment are part of this change.
