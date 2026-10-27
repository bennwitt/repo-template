# repo-template quick commands

**Usual order: update the machine, then update each adopted repository.**
Replace example paths and pack names with yours. Full walkthrough:
[machine and repository setup](HOW_TO_UPDATE_MACHINE_AND_ITS_REPOS.md).

## Update this machine

Start with a clean standards checkout (`git status --short` should print nothing).
Stop and resolve any error before running the next command.

```bash
cd "${AI_DEV_STANDARDS:-$HOME/aiDevStandards}"
git status --short
git switch main
git pull --ff-only
repo-template globals --check    # preview machine changes
repo-template globals            # apply skills, settings, MCP servers and Git ignores
```

The editable CLI installation picks up pulled code changes automatically. Restart Claude Code
and Codex to load updated settings and servers. Repositories still need their own update below.

## Update an adopted repository

For your own repository, start with a clean working tree and create a branch:

```bash
cd /path/to/repo
git status --short
git switch main                  # use the repository's default branch
git pull --ff-only
git switch -c chore/repo-template-update
repo-template check .            # preview; "Standards are current." means no work
repo-template update .           # apply and resolve any prompts
repo-template check .            # verify
git diff                        # review before committing
git status --short               # includes new files to review
```

Later updates remember the profile and packs; no adoption flags are needed.
For a **personal** adoption, run only `check`, `update`, `check` in the repository:
there is no standards change to commit or branch for.

Check several repositories at once (update each separately):

```bash
repo-template check ~/code/service-a ~/code/web-b ~/code/tool-c
```

## Adopt an existing repository

Run at the repository root. Choose **one** pair; start a branch for full or packs-only adoption.

```bash
# Your Python/uv repository: full engineering baseline
repo-template check .
repo-template update .

# Your other-stack repository: skills and pack MCP servers only
repo-template check . --packs-only --pack typescript
repo-template update . --packs-only --pack typescript

# A team's repository: personal setup, nothing for the team to commit
repo-template check . --personal --pack typescript
repo-template update . --personal --pack typescript
```

Finish with `repo-template check .`. Personal adoption requires the main, non-sparse checkout;
it does not support linked worktrees or repositories already adopted for the team.

## Add or remove skill packs

```bash
repo-template globals --list packs       # pack descriptions, members and MCP servers
repo-template globals --list skills      # individual skills and descriptions
repo-template globals --list --repo .    # show this repository's selections
repo-template globals --list --json      # JSON for scripts
repo-template update . --select          # interactive picker → preview → confirm
```

In the picker: toggle numbers or `pack:NAME` / `skill:NAME`; `packs`, `skills`, `all` or
`/search` changes the view; `done` previews; `q` cancels. Add `--packs-only` or `--personal`
for first adoption where appropriate. Existing profiles are remembered. A full-baseline
update also previews and applies baseline changes. Global skills are installed by `globals`.

Available packs: [catalog](README.md#catalog-every-skill-where-it-applies-and-where-it-comes-from).
In an adopted repository:

```bash
repo-template check . --pack security                # preview adding a pack
repo-template update . --pack security               # add it
repo-template update . --pack typescript --pack react # add several
repo-template check .
```

```bash
repo-template check . --skill code-simplification
repo-template update . --skill code-simplification    # one skill, no sibling skills or pack MCP
repo-template update . --remove-skill code-simplification
repo-template update . --remove-pack security
```

Individual choices are recorded under `individual_skills` alongside `skill_packs`. Removing
one choice keeps skills still supplied by another. Selection works with all adoption profiles;
`new` also accepts `--skill`.

For the [evaluated engineering workflows](docs/skill-evaluation.md):

```bash
repo-template update . --pack delivery    # quality constraints, source checks, release readiness
repo-template update . --pack performance # measured optimization and web-performance audits
repo-template update . --pack api --pack sre # retry contracts and feature instrumentation
```

`dev-workflows` also supplies simplification and deprecation/migration. Invoke installed skills
by their names; Addy's nine command aliases are not installed. Read the
[workflow guide](docs/agents/workflow.md) for the preferred route. `setup-matt-pocock-skills`
configures missing tracker/triage/domain choices; it does not install the skills or gate ordinary
testing and local-spec reviews. Full-baseline updates seed the guide without overwriting edits.
Changed derived inputs in `globals --upstream` need a manual merge, not `globals --upgrade`.

## Create a Python/uv repository

```bash
repo-template new my-service --parent ~/code --description "My service"
cd ~/code/my-service
uv sync --dev
uv run pytest
```

Fill in Purpose and Boundaries in `AGENTS.md`. Add `--pack NAME` to `new` if needed.
This creates local files and initializes Git; it does not create a GitHub repository or commit.

## Run project checks

For the full Python/uv baseline, run before committing:

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
repo-template check .
```

To fix formatting: `uv run ruff format .`. Keep bulk formatters out of vendored
`.agents/skills/` and `.agents/packs/`; upstream files must retain their recorded bytes.

## Review upstream updates (standards maintainers)

Run once in a clean standards checkout on a maintenance branch. These commands contact upstream;
`--upgrade` changes the shared catalog and requires review, checks and a commit/PR.

```bash
cd "${AI_DEV_STANDARDS:-$HOME/aiDevStandards}"
git switch -c chore/upgrade-skills
repo-template globals --upstream           # report available updates; read-only
repo-template globals --upgrade            # interactively review changed skills
repo-template globals --check              # validate the resulting catalog and machine state
```

Targeted alternatives: `repo-template globals --upgrade tdd wizard` for named skills,
or `repo-template globals --upgrade mcp:shadcn` for an MCP server pin.
After merging, other machines use **Update this machine** above.
[Full upgrade workflow](README.md#add-update-or-remove-a-skill).

## Setup, help and quick fixes

```bash
repo-template --version                    # CLI version and installation checkout
repo-template --help
repo-template update --help
repo-template globals --help
bash "${AI_DEV_STANDARDS:-$HOME/aiDevStandards}/setup-machine.sh" --check --offline
claude mcp list                            # inspect connected servers
```

| Situation | Next step |
| --- | --- |
| First setup or missing CLI | Run `bash setup-machine.sh` from the standards checkout; follow its prompts. |
| CLI points at the wrong checkout | Run `uv tool install --editable --force /path/to/standards`; set `AI_DEV_STANDARDS` to that same path in your shell profile. |
| `update` exits 2 / preserved files | Rerun in a terminal. Choices: `o` baseline, `k` keep yours, `m` merge, `a` always keep yours, `s` skip. Read other `!` lines for their fixes. |
| `newer than this repo-template` | Update this machine first, then retry. |
| `differs from … as vendored` | In the standards checkout, inspect `git status --short` and `git diff -- .agents/skills .agents/packs`. Back up local changes before restoring affected files; do not change lock hashes to hide the mismatch. |
| `globals` says a local setting was kept | Review the reported setting; your machine's choice was preserved. |

More fixes: [troubleshooting](HOW_TO_UPDATE_MACHINE_AND_ITS_REPOS.md#troubleshooting).
