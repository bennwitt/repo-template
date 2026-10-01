---
name: repo-template
description: "Apply and maintain the repo-template baseline in a repository: plan with `repo-template check`, apply with `update`, resolve the files it preserves for manual review (exit code 2), add skill packs, or start a repository with `new`. Use when asked to bring a repository up to standard or update its standards, when repo-template reports preserved files, or to add a skill pack."
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
   - Exit 1: an error line names a missing tool (git, uv) or a failed `uv lock`. Fix it, rerun.
   - Exit 2: go to step 3.
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
   - **`CLAUDE.md (now AGENTS.md …)`**: the agent guide lives in `CLAUDE.md`, so Codex can't
     read it. `git mv CLAUDE.md AGENTS.md`, then write a new `CLAUDE.md` containing only
     `@AGENTS.md`.
   - **`CONTEXT.md (now GLOSSARY.md …)`**: `git mv CONTEXT.md GLOSSARY.md`, move the Purpose and
     Boundaries sections into `AGENTS.md`, and keep only terms in the glossary, in the format the
     `domain-modeling` skill describes. Then repoint every reference: `git grep -n CONTEXT.md`.
   - **`(not a link …)`**: a real folder sits where a skill link belongs. Ask the user before
     moving it.

   Rerun `repo-template update <repo>`; this step is done when it exits 0.
4. **Verify and commit.** Run the repository's checks (`uv run pytest`, `uv run ruff check .`,
   `uv run mypy src`), then `repo-template check <repo>` must print "Standards are current."
   Commit everything in one commit, including `.repo-template.json` and `uv.lock`.

Keep the default hook and lockfile steps. `--no-hooks` and `--no-lock` exist for repositories
where another system owns the Git hooks or the lockfile.

## Skill packs

Domain skills (LangChain, Gradio, knowledge graphs, TypeScript) load only in repositories that
list their pack; `~/.agents/skill-packs.json` defines the packs. Add one when the repository uses
that framework: `repo-template update <repo> --pack <name>` records it under `skill_packs` in
`.repo-template.json` and links its skills into the repository's `.claude/skills/`, which Git
ignores. To remove a pack, delete it from `skill_packs` and run `update`.

## New repositories

`repo-template new <name> --parent <dir> --description "<one line>"`, plus `--pack <name>` for
each pack the project needs. It refuses a non-empty directory. Then fill in the Purpose and
Boundaries sections of the new `AGENTS.md`, and run `uv run pytest` to confirm the baseline works.

## The manifest

`.repo-template.json` records the template version, the project variables, each managed file's
hash as generated, and two lists that belong to the project: `skill_packs` and `project_owned`.
Edit only those two lists; `update` maintains the rest.
