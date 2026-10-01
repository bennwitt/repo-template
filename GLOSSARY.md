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
A baseline file written once if missing, which then belongs to the project.
_Avoid_: starter file

**Merged file**:
A baseline file that `update` extends with missing entries and never removes from:
`pyproject.toml`, `.gitignore`, and the VS Code JSON files.
_Avoid_: patched file

**Manifest**:
`.repo-template.json` in a generated repository: the template version, the project variables, and
the hash of each file as generated.
_Avoid_: lock, state file

### Machines and skills

**Portable global**:
A skill, hook, or setting that is safe to version and use on every machine.
_Avoid_: dotfile

**Machine state**:
Credentials, sessions, caches, and local preferences that must stay on one machine.
_Avoid_: local config

**Skill catalog**:
The skills in `.agents/skills/`, linked into every machine by `globals`.
_Avoid_: skill library

**Skill pack**:
A named group of catalog skills, defined in `.agents/skill-packs.json`, that are linked only into
repositories whose manifest lists the pack, not into every machine.
_Avoid_: skill bundle, plugin

**Skill mirror**:
`.claude/skills/` in the standards repository: one relative link per catalog skill.

**Receipt policy**:
`.ai/receipt-policy.json`: whether a repository records skill receipts, and where.

**Skill receipt**:
One recorded use of a skill in a repository, appended by the receipt hook.
_Avoid_: skill log entry, audit event
