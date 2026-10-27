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
     or pre-push hook): render a pristine baseline with
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
where another system owns the Git hooks or the lockfile. When the repository already fills in
pull request descriptions itself (a workflow such as `.github/workflows/pr-template.yml`, or a
post-commit hook that drafts one), it races the baseline's pre-push hook for a blank
description: ask the user which to keep. To keep theirs, delete `.githooks/pre-push` and add it
to `project_owned`.

## Every repository on this machine

1. **Find them.** Ask which folders hold the user's repositories, unless they said. Resolve
   each folder's links first (`cd <folder> && pwd -P`), then list the adopted repositories in
   the resolved folders:
   `find <resolved>... -maxdepth 6 \( -name node_modules -o -name .venv \) -prune -o -name .git -type d -prune -exec sh -c 'test -f "$1/repo-template.json"' sh {} \; -print -o -name .repo-template.json -print 2>/dev/null`.
   Each repository is the folder above a printed path (a `.git` folder is a personal
   repository's). Leave out the standards checkout, `dirname "$(readlink ~/.agents)"`:
   `setup-machine.sh` keeps it current on `main`. A repository with no manifest isn't adopted:
   leave it out unless the user asks to adopt it.
2. **Plan.** `repo-template check <repo> <repo> ...` prints one line each: `current`, or what
   `update` would do there. Show the user the lines that aren't current; this step is done when
   they have said which to update (all of them, unless they say otherwise).
3. **Update them one at a time**, each by the path its profile picks (**Choose the path
   first**): a personal repository in place; the others on a branch started from an up-to-date
   default branch (`git switch main && git pull --ff-only`), verified and committed as step 4 of
   **Bring a repository to standard** says. A repository that can't switch branches, or stops on
   something only the user can decide, waits for the end; go on with the next.
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
**Bring a repository to standard**. To drop a pack, use `update --remove-pack <name>`; to undo it, set both
`skill_packs` and `individual_skills` to `[]` in `.git/repo-template.json`, rerun `update`,
then delete that file.

## Skill packs

Browse with `repo-template globals --list packs` or `--list skills`; add `--repo <repo>`
to mark explicit selections, or `--json` for scripts. Listing is read-only. In a terminal,
`repo-template update <repo> --select` starts with existing choices: toggle numbers or
`pack:NAME` / `skill:NAME`, filter with `/search`, and use `done` to preview before confirming.
Cancel with `q`, EOF or Ctrl-C. A full-profile preview includes baseline changes as well.
For agents and scripts, use `check` then `update --no-input` with repeatable `--pack`, `--skill`,
`--remove-pack` and `--remove-skill`; the picker requires a terminal. First adoption still
needs the appropriate profile flag. Global skills are handled by `globals`.

Individual selections live in `individual_skills` alongside `skill_packs`. They bring a
skill's resources, but not siblings or pack MCP servers; choose the pack if those are needed.
Removing one selection preserves skills still supplied by another selection. Version 0.6.0
protects these manifests from older CLIs. New repositories also accept `--skill`.

Domain skills (LangChain, Gradio, knowledge graphs, TypeScript) load in repositories selecting
the skill or its pack; `~/.agents/skill-packs.json` defines the packs. Add one when the repository uses
that framework: `repo-template update <repo> --pack <name>` records it under `skill_packs` and
links its skills into the repository's `.claude/skills/` (Claude Code) and `.agents/skills/`
(Codex), where Git ignores them. To remove a pack, run `update --remove-pack <name>`. Add `dev-workflows` only when the user asks for it: its review,
debugging, testing,
architecture and requirements skills overlap global ones. The pack also includes standalone
Ponytail, invoked explicitly with `/ponytail full` for the smallest complete implementation
(`lite` presents the smaller option; `ultra` challenges scope). Say "stop ponytail" to end its
session mode. Its plugin hooks and dashboard are not installed. `atlassian` needs an Atlassian
MCP server the user connects and signs in to; the pack ships none.

Eight Addy-derived skills complement the core Pocock workflow. Choose `delivery` for quality
constraints, version-verified implementation and release readiness; `performance` for measured
optimization and source-only web audits; `api` for compatibility and retry/idempotency contracts;
`sre` for feature instrumentation; `dev-workflows` for simplification and deprecation/migration.
Add only relevant packs. They install skills by name, not Addy's plugin commands or hooks.
Release readiness assesses evidence and recovery; it does not authorize deployment.

`globals --upstream` checks derived source paths, companion inputs and licenses. Changed derived
inputs require a manual merge preserving local corrections; `--upgrade` does not replace them.
Use `docs/skill-evaluation.md` in the standards repository for the complete selection rationale.

The `security` pack includes Cloudflare's explicitly invoked `/security-audit` alongside the
routine `security-reviewer`. For an audit, state scope, profile (`quick`, `standard`, `deep`),
and an agent-invocation budget. Full audits need Node.js and subagents. Target execution needs
the skill's OS-enforced sandbox and artifact-promotion controls; the pack does not install them.
Missing controls leave affected findings as `needs_validation`. Reports default outside the
target at `~/security-audit-skill/<repo-name>/run-<N>`.

## New repositories

`repo-template new <name> --parent <dir> --description "<one line>"`, plus `--pack <name>` for
each pack the project needs. It refuses a non-empty directory. Then fill in the Purpose and
Boundaries sections of the new `AGENTS.md`, and run `uv run pytest` to confirm the baseline works.

Full-baseline repositories receive `docs/agents/workflow.md` as a seed. New AGENTS files point
to it; existing AGENTS and edited guides stay untouched. Offer the pointer for an existing guide
only when relevant. Packs-only/personal adoption writes no project guidance. The setup skill
configures missing tracker/triage/domain choices for installed workflows, not the skills themselves.
Use `setup-matt-pocock-skills` only when those conventions are needed; local specs, ordinary tests
and debugging need no tracker setup. Keep CLAUDE import stubs and shared AGENTS authority intact.

## The manifest

`.repo-template.json` records the template version, the project variables, each managed file's
hash as generated, and the lists that belong to the project. Edit only `skill_packs`, `individual_skills`,
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
