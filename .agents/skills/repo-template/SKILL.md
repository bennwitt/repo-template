---
name: repo-template
description: "Apply and maintain the repo-template baseline in a repository: plan with `repo-template check`, apply with `update`, resolve files it preserves (exit 2), add skill packs, or start one with `new`. Use when bringing a repository up to standard, when repo-template reports preserved files, or to add a pack."
---

# repo-template

`repo-template` renders a project baseline into repositories and never overwrites what a project
changed: it preserves the file and reports it. `repo-template --help` lists every flag; this skill
covers the judgement calls the CLI leaves to you.

If `repo-template` isn't on `PATH`, install it from the standards repository behind `~/.agents`:
`uv tool install --editable "$(dirname "$(readlink -f ~/.agents)")"`.

## Bring a repository to standard

1. **Plan.** Start from a clean working tree (`git status`), so the final commit holds only
   standards changes. Run `repo-template check <repo>`. Exit 0 means the repository is current:
   stop here. Otherwise read the plan: `+` create, `~` update, `-` remove, `!` preserved.
2. **Apply.** Run `repo-template update <repo>`.
   - Exit 0: go to step 4.
   - Exit 1: fix what an error line says, then rerun. Errors win over preserved files, so a
     run can exit 1 with `!` lines too: fix the error first.
     - `x` lines: a missing tool (git, uv), a failed `uv lock`, or `skill pack '<name>' is listed
       in .repo-template.json but not defined`. For that last one, `git pull` the standards
       repository behind `~/.agents` and run `repo-template globals`, or remove the pack from
       `skill_packs` if it was renamed or dropped. A machine still on a version before 0.4.2
       (`~/.claude/settings.json` is a link) follows the README's "Upgrading a machine from a
       linked settings file" instead of a plain pull.
     - A `repo-template: error:` line means the command couldn't run at all: `--pack` named an
       unknown pack, the manifest doesn't parse, or the manifest was written by a newer version
       (`git pull` the standards repository).
   - Exit 2: go to step 3. (A person running `update` in a terminal is asked about each file
     instead, with a diff and the choice to use the baseline, keep, merge or skip. When the user
     is at a terminal, offering that is often faster than step 3.)
3. **Resolve every preserved file** (each `!` line), by case:
   - **A managed file that differs** (CI workflow, Dependabot config, PR template, pre-commit
     hook): render a pristine baseline with
     `repo-template new <name> --parent "$(mktemp -d)" --no-git --no-lock` and diff the two.
     In a repository the baseline didn't generate, every differing managed file lands here,
     because no generation hash proves it unedited. Decide each file:
     - the difference is cosmetic, or the baseline is stricter (SHA-pinned actions,
       `permissions`, `--locked`): copy the baseline version over it;
     - the project made a deliberate choice: merge the baseline's improvements into the project's
       file, then add the path to `project_owned` in `.repo-template.json`;
     - the intent is unclear: ask the user which version wins.
   - **`(invalid JSON)` or `(invalid TOML)`**: the file doesn't parse; VS Code files with comments
     or trailing commas are the usual cause. Rewrite it as strict JSON or TOML with every setting
     kept; Claude Code may ask the user to approve edits under `.vscode/`.
   - **`(couldn't merge the baseline's entries)`**: the file is valid, but its layout defeated the
     merge. Add what the baseline wants by hand (compare with the pristine baseline's
     `pyproject.toml`: missing dev dependencies, tool tables for tools the project doesn't
     configure), then rerun.
   - **`CLAUDE.md (now AGENTS.md …)`**: the agent guide lives in `CLAUDE.md`, so Codex can't
     read it. `git mv CLAUDE.md AGENTS.md`, then write a new `CLAUDE.md` containing only
     `@AGENTS.md`.
   - **`CONTEXT.md (now GLOSSARY.md …)`**: `git mv CONTEXT.md GLOSSARY.md`, move the Purpose and
     Boundaries sections into `AGENTS.md`, and keep only terms in the glossary, in the format the
     `domain-modeling` skill describes. Then repoint every reference: `git grep -n CONTEXT.md`.
   - **`(not a link …)`**: a real folder sits where a skill link belongs. Ask the user before
     moving it.
   - **`~/.claude/settings.json … (changed on this machine; kept)`** or **`(removed on this
     machine)`** (from `globals`): a portable setting differs on this machine. It is reported once.
     Ask the user whether to keep the local choice (nothing to do) or take the standard's value
     (set the entry to the value in `.agents/claude-settings.json`, or re-add the rule).
   - **`~/.claude/settings.json (a link to …, which repo-template didn't create …)`**: the user
     manages that file elsewhere (dotfiles). Leave it unless they ask.

   Rerun `repo-template update <repo>`; this step is done when it exits 0. An exit 1 goes back to
   step 2's exit-1 handling.
4. **Verify and commit.** Run the repository's checks (`uv run pytest`, `uv run ruff check .`,
   `uv run mypy src`), then `repo-template check <repo>` must print "Standards are current."
   Commit everything in one commit, including `.repo-template.json` and `uv.lock`.

Keep the default hook and lockfile steps. `--no-hooks` and `--no-lock` exist for repositories
where another system owns the Git hooks or the lockfile.

## Skill packs

Domain skills (LangChain, Gradio, knowledge graphs, TypeScript) load only in repositories that
list their pack; `~/.agents/skill-packs.json` defines the packs. Add one when the repository uses
that framework: `repo-template update <repo> --pack <name>` records it under `skill_packs` in
`.repo-template.json` and links its skills into the repository's `.claude/skills/` (Claude Code)
and `.agents/skills/` (Codex), where Git ignores them. To remove a pack, delete it from
`skill_packs` and run `update`. Read what `update` preserves: a link it can't own is reported,
not replaced.

## New repositories

`repo-template new <name> --parent <dir> --description "<one line>"`, plus `--pack <name>` for
each pack the project needs. It refuses a non-empty directory. Then fill in the Purpose and
Boundaries sections of the new `AGENTS.md`, and run `uv run pytest` to confirm the baseline works.

## The manifest

`.repo-template.json` records the template version, the project variables, each managed file's
hash as generated, and two lists that belong to the project: `skill_packs` and `project_owned`.
Edit only those two lists; `update` maintains the rest.
