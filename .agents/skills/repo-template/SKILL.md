---
name: repo-template
description: "Apply and maintain the repo-template baseline: choose full, packs-only or personal, plan with `repo-template check`, apply with `update`, resolve preserved files (exit 2), add skill packs, or start one with `new`. Use when bringing a repository up to standard, updating every repository on a machine, adopting a team's repository, or adding a pack."
---

# repo-template

`repo-template` renders a project baseline into repositories and never overwrites what a project
changed: it preserves the file and reports it. `repo-template --help` lists every flag; this skill
covers the judgement calls the CLI leaves to you.

If `repo-template` isn't on `PATH`, the machine isn't set up: ask the user to run
`setup-machine.sh` from the standards repository (`HOW_TO_UPDATE_MACHINE_AND_ITS_REPOS.md`,
section 1).

## Choose the path first

Read the profile: `grep -h '"profile"' <repo>/.repo-template.json <repo>/.git/repo-template.json 2>/dev/null`

- `personal`: follow **A team's repository**.
- `python-uv` or `packs-only`: follow **Bring a repository to standard**. Every run follows the
  recorded profile, so pass no adoption flag.
- No manifest: find out whose repository it is before anything runs
  (`git -C <repo> log --format='%an' | sort | uniq -c | sort -rn | head`).
  - Other people commit to it: follow **A team's repository**. When unsure, ask the user.
  - The user's own, without a `pyproject.toml` (another stack): adopt it packs-only with
    `--packs-only --pack <name>` in step 1 and 2 below.
  - The user's own Python/uv repository: **Bring a repository to standard**.

## Bring a repository to standard

1. **Plan.** Start from a clean working tree (`git status`) on a branch
   (`chore/repo-template-update`), so the final commit holds only standards changes. Run
   `repo-template check <repo>`. Exit 0 means the repository is current: stop here. Otherwise
   read the plan: `+` create, `~` update, `-` remove, `!` preserved.
2. **Apply.** Run `repo-template update --no-input <repo>`.
   - Exit 0: go to step 4.
   - Exit 1: fix what an error line says, then rerun. Errors win over preserved files, so a
     run can exit 1 with `!` lines too: fix the error first.
     - `x` lines: a missing tool (git, uv), a failed `uv lock`, or `skill pack '<name>' is listed
       in the repository's manifest but not defined`. For that last one, pull the standards
       repository (`git -C "$(dirname "$(readlink ~/.agents)")" pull --ff-only`) and run
       `repo-template globals`, or remove the pack from `skill_packs` if it was renamed or
       dropped.
     - A `repo-template: error:` line means the command couldn't run at all: `--pack` named an
       unknown pack, the manifest doesn't parse, or the manifest was written by a newer version
       (pull the standards repository).
   - Exit 2: go to step 3.
3. **Resolve every preserved file** (each `!` line), by case:
   - **A managed file that differs** (CI workflow, Dependabot config, PR template, pre-commit
     hook): render a pristine baseline with
     `repo-template new <name> --parent "$(mktemp -d)" --no-git --no-lock` and diff the two.
     In a repository the baseline didn't generate, every differing managed file lands here,
     because no generation hash proves it unedited. Decide each file:
     - the difference is cosmetic, or the baseline is stricter (SHA-pinned actions,
       `permissions`, `--locked`): copy the baseline version over it;
     - the project made a deliberate choice that should hold for good: merge the baseline's
       improvements into the project's file, then add the path to `project_owned` in
       `.repo-template.json`;
     - the project's version should stay, but a later baseline change should still come up:
       that is an accepted difference, and only `k` in a terminal records it. Ask the user to run
       `repo-template update <repo>` in their own terminal for that file;
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
   - **`(Git wouldn't ignore this link; …)`**: the machine's global Git ignore doesn't reach this
     repository. Ask the user to run `repo-template globals` (it writes the ignore block into the
     file Git reads), or add `.claude/`, `.agents/` and `.codex/` to the repository's `.gitignore`.
   - **`(not a link …)`, `(a link this tool didn't make …)`, `(edited in this repository; kept)`**:
     something of the project's sits where repo-template would write. Ask the user before
     removing or replacing it.

   Rerun `repo-template update --no-input <repo>`; this step is done when it exits 0. An exit 1
   goes back to step 2's exit-1 handling.
4. **Verify and commit, by profile.** `repo-template check <repo>` must print "Standards are
   current." Then:
   - `python-uv`: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` and
     `uv run mypy src` pass; commit everything in one commit, including `.repo-template.json`
     and `uv.lock`.
   - `packs-only`: commit `.repo-template.json`, and `.mcp.json` when a pack has servers.

Keep the default hook and lockfile steps. `--no-hooks` and `--no-lock` exist for repositories
where another system owns the Git hooks or the lockfile.

## Every repository on this machine

1. **Find them.** Ask which folders hold the user's repositories, unless they said. Then list the
   adopted ones:
   `find <folder>... -maxdepth 6 \( -name node_modules -o -name .venv \) -prune -o \( -name .repo-template.json -o -path '*/.git/repo-template.json' \) -print 2>/dev/null`.
   Each repository is the folder holding `.repo-template.json`, or the one above `.git`. A
   repository with neither isn't adopted: leave it out unless the user asks to adopt it.
2. **Plan.** `repo-template check <repo> <repo> ...` prints one line each: `current`, or what
   `update` would do there. Show the user the lines that aren't current; this step is done when
   they have said which to update (all of them, unless they say otherwise).
3. **Update them one at a time**, each by the path its profile picks (**Choose the path
   first**): a personal repository in place, the others on a branch, verified and committed as
   step 4 of **Bring a repository to standard** says. A repository that stops on something only
   the user can decide waits for the end; go on with the next.
4. **Report** one row per repository: its profile, and the outcome (current; updated, with the
   branch and commit; or waiting, with the decision it needs). Pushing and opening pull requests
   stay with the user: offer them one repository at a time.

## A team's repository

Keep every change on this machine: nothing is committed, and teammates never see a file of it.

1. Save `git -C <repo> status --short` to compare with later.
2. Preview with `repo-template check <repo> --personal --pack <name>`, then run
   `repo-template update --no-input <repo> --personal --pack <name>` (later runs need neither
   flag). The manifest goes to `.git/repo-template.json`, the links into `.git/info/exclude`,
   and the MCP servers to Claude Code's local scope.
3. The step is done when `git -C <repo> status --short` matches what you saved and
   `repo-template check <repo>` prints "Standards are current."

If it refuses: in a subfolder, rerun at the top of the checkout; in a linked worktree, run it in
the main checkout; in a sparse checkout, tell the user personal adoption isn't supported there;
when the repository has its own `.repo-template.json`, it is adopted for everyone: follow
**Bring a repository to standard**. To drop a pack, edit `skill_packs` in
`.git/repo-template.json` and rerun `update`; to undo it, set the list to `[]`, rerun `update`,
then delete that file.

## Skill packs

Domain skills (LangChain, Gradio, knowledge graphs, TypeScript) load only in repositories that
list their pack; `~/.agents/skill-packs.json` defines the packs. Add one when the repository uses
that framework: `repo-template update <repo> --pack <name>` records it under `skill_packs` and
links its skills into the repository's `.claude/skills/` (Claude Code) and `.agents/skills/`
(Codex), where Git ignores them. To remove a pack, delete it from `skill_packs` and run
`update`.

## New repositories

`repo-template new <name> --parent <dir> --description "<one line>"`, plus `--pack <name>` for
each pack the project needs. It refuses a non-empty directory. Then fill in the Purpose and
Boundaries sections of the new `AGENTS.md`, and run `uv run pytest` to confirm the baseline works.

## The manifest

`.repo-template.json` records the template version, the project variables, each managed file's
hash as generated, and the lists that belong to the project. Edit only `skill_packs`,
`project_owned`, and names in `mcp_kept` (delete one to have repo-template manage that MCP
entry again); `update` maintains the rest.

## Output from `globals`

- **`~/.claude/settings.json … (changed on this machine; kept)`**, **`(removed on this
  machine)`** or **`… (configured by hand; kept)`**: a portable setting or MCP entry differs on
  this machine. It is reported once. Ask the user whether to keep the local choice (nothing to
  do) or take the standard's value (set the entry to the value in
  `.agents/claude-settings.json` or `.agents/mcp-servers.json`, or re-add the rule).
- **`~/.claude/settings.json (a link to …, which repo-template didn't create …)`**: the user
  manages that file elsewhere (dotfiles). Leave it unless they ask.
- **`~/.claude/settings.json` is a link into a standards checkout** (a machine set up before
  0.4.2): follow Appendix A, step 1, of `HOW_TO_UPDATE_MACHINE_AND_ITS_REPOS.md`.
- Before changing a machine, run `repo-template globals --check`, and `globals` only once the
  user agrees.
