# repo-template

The single maintained source for repository engineering defaults and portable AI-development
configuration across machines.

## Language

### Repositories and files

**Standards repository**:
This Git repository: the CLI, the project baseline, and the portable globals it links into each
machine.
_Avoid_: template repo, dotfiles

**Project baseline**:
The full set of files rendered into a new or existing application repository.
_Avoid_: template, scaffold, skeleton

**Managed file**:
A baseline file that `update` may upgrade only while it is unchanged since generation.
_Avoid_: generated file, owned file

**Seed file**:
A baseline file created whenever it is missing, which then belongs to the project: `update`
never changes one that exists.
_Avoid_: starter file

**Merged file**:
A baseline file that `update` extends with missing entries and never removes from:
`pyproject.toml`, `.gitignore`, and the VS Code JSON files.
_Avoid_: patched file

**Manifest**:
`.repo-template.json` in a repository repo-template manages: its profile, template version, skill
packs, individual skill selections and pack MCP records; for the Python/uv profile also the project variables and the hash of
each file as generated. A personal repository's is `.git/repo-template.json`, with no MCP
records (those are in `~/.repo-template/globals-state.json`).
_Avoid_: lock, state file

**Profile**:
What a manifest says repo-template manages: `python-uv` (the full project baseline),
`packs-only` (selected packs, individual skills and pack MCP servers) or `personal` (the same, for one person). It is
recorded on adoption, and later runs follow it.

**Adoption**:
The first `update` of a repository the baseline didn't create; it records the profile.
_Avoid_: onboarding, migration

**Preserved file**:
A file `update` (or `globals`) leaves for a decision instead of changing it: a `!` line under
"Preserved for manual review", and exit 2.
_Avoid_: conflict, kept file

**Project-owned file**:
A path in the manifest's `project_owned`: `update` never changes or recreates it. A seed file
belongs to the project too, but isn't project-owned until listed.
_Avoid_: owned file

**Accepted difference**:
A managed file the project keeps in its own form, recorded in the manifest with its hash and the
baseline's hash, so `update` stays quiet until either one changes.
_Avoid_: exception, waiver

### Machines and skills

**Portable global**:
A skill, hook, or setting that is safe to version and use on every machine.
_Avoid_: dotfile

**Portable settings**:
The `portable` part of `.agents/claude-settings.json`: plugin switches, environment variables,
marketplaces, permission rules and hooks (each inside its event and matcher) that `globals`
merges into every machine's `~/.claude/settings.json`, keeping entries changed on that machine.
_Avoid_: shared settings, settings link

**Machine default**:
A setting in the `defaults` part of `.agents/claude-settings.json` (model, effort, theme,
notifications): written once, when a machine doesn't have it, then left to that machine.

**Machine state**:
Credentials, sessions, caches, and local preferences that must stay on one machine.
_Avoid_: local config

**Skill catalog**:
The skills in `.agents/skills/` (global, linked into every machine by `globals`) and
`.agents/packs/` (pack skills, linked into repositories selecting the skill or its pack).
_Avoid_: skill library

**Skill pack**:
A named group of catalog skills, defined in `.agents/skill-packs.json` and kept in
`.agents/packs/`. Selecting a pack supplies all its members in the repository
(`.claude/skills/` for Claude Code and `.agents/skills/` for Codex); members can also be
selected individually. Pack skills are not installed globally.
_Avoid_: skill bundle, plugin

**Individual selection**:
A repository skill chosen with `--skill`, recorded in the manifest's `individual_skills`.
It supplies that skill and its supporting files, without sibling skills or pack MCP servers.
Effective repository skills are the union of individual selections and selected pack members.

**Packs-only repository**:
A repository adopted with `update --packs-only`: its manifest's profile is `packs-only`, and
repo-template manages only selected packs, individual skills and pack MCP servers, never baseline files.
_Avoid_: partial adoption

**Personal repository**:
A repository someone else manages, adopted with `update --personal` for one person's skill packs:
nothing anyone else sees changes. Its manifest, ignore entries and MCP servers stay on that
person's machine (`.git/`, Claude Code's local scope).
_Avoid_: private adoption, local adoption

**Cooldown**:
The 7 days a package release must be public before repo-template pins it (MCP servers, tools).
Upstream skill revisions don't wait; they are reviewed and scanned instead.

**MCP catalog**:
`.agents/mcp-servers.json`: each MCP server once, with what it runs, its pin, its denied tools
and why. A global server is installed on every machine; a pack server comes with a pack.

**Tool pins**:
`.agents/machine-tools.json`: the CLIs the skills and plugins drive on each machine, each pinned
once (npm by version, a GitHub release by version and each platform's asset SHA-256).
`setup-machine.sh` installs from it; `globals --upstream` reports newer releases.
_Avoid_: machine tools list, tool versions file

**Re-pin**:
`globals --upgrade mcp:<name>`: moving an MCP server's pin to its newest final release past the
cooldown, its args, version and `publishedAt` together.

**Kept entry**:
An MCP entry repo-template would manage but leaves alone, because it was changed or removed by
hand: reported once, then recorded (in `globals-state.json`, or a repository's `mcp_kept`).

**Skill sources**:
`.agents/skill-sources.json`: each source repository's license, copyright and pinned license
texts, the upstream commit of each vendored skill, the local skills and what they derive from,
skills deliberately not vendored, and skills allowed to run commands when they load. With the
lock, it is the catalog's provenance.

**Catalog integrity**:
Every vendored skill hashes to its lock entry, with nothing untracked in it (an override may
change only its own frontmatter fields, to exactly what it writes), and every skill is recorded
and licensed. `globals --check` and the tests verify it offline; a skill that fails isn't
linked.

**Catalog upgrade**:
`globals --upgrade`: vendoring a skill from upstream, refreshed or added. Each one is staged,
verified against the upstream tree SHA, scanned by the committed `skill-scanner`, shown as a diff,
and swapped in only when you apply it. `globals --upstream` reports what an upgrade would bring.

**Skill override**:
A frontmatter edit to a vendored skill, kept in `.agents/skill-overrides.json` with the upstream
text of each field it replaces and the upstream SKILL.md's blob SHA, marked in the SKILL.md, and
re-applied by `globals` after the skill is vendored again.

**Derived skill**:
A locally maintained adaptation of an upstream skill, with its source, reviewed revision and
license recorded. Its body can differ from upstream; source changes require a reviewed merge.
_Avoid_: vendored skill, override

**Workflow guide**:
A project's choices about which skills to use, what their review scope includes and when
repository-specific configuration is needed. It belongs to the project after creation.
_Avoid_: universal router, installer

**Skill mirror**:
`.claude/skills/` in the standards repository: one relative link per global skill (pack skills
aren't mirrored).

**Receipt policy**:
`.ai/receipt-policy.json`: whether a repository records skill receipts, and where.

**Skill receipt**:
One recorded use of a skill in a repository, appended by the receipt hook.
_Avoid_: skill log entry, audit event
