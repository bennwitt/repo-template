# repo-template

**One standard for every repository you start and every machine you code on, built so AI coding
agents (Claude Code, Codex) find what they need and do their best work.**

`repo-template` is two things that belong together:

1. **A CLI that creates and safely updates Python/uv repositories.** A new repository comes out
   ready to work in: uv, pytest, Ruff, strict mypy, CI, Dependabot, a pre-commit secret scan,
   and the context files agents read first (`AGENTS.md`, `CONTEXT.md`, `docs/adr/`). Existing
   repositories move toward the same standard without losing local changes.
2. **A versioned catalog of agent skills and settings.** `.agents/skills/` holds the skills you
   rely on: test-driven development, bug diagnosis, architecture review, spec → tickets →
   implementation, code review, LangChain/LangGraph, evals and more. One command links them
   into Claude Code and Codex on any machine.

## Why this exists

AI agents are only as good as the repository they land in and the workflows they're given.

- **Agents need context in predictable places.** An `AGENTS.md` with the real commands, a
  `CONTEXT.md` glossary, and ADRs that explain past decisions give an agent the context a new
  teammate would ask for. Skills such as `domain-modeling`, `codebase-design`,
  `improve-codebase-architecture` and `grill-with-docs` read and write exactly these files.
  Every generated repository has them.
- **Agents need a fast, strict feedback loop.** `tdd` and `diagnosing-bugs` work only when tests,
  lint and type checks fail loudly. Every repository gets the same `pytest` / `ruff` /
  `mypy --strict` loop, enforced by a pre-commit hook and CI.
- **Copied templates rot.** Cookiecutter-style templates are copied once and then drift.
  `repo-template update` keeps bringing repositories forward, and because it records what it
  generated, it never overwrites a change you made.
- **Skills drift between machines.** Hand-copying `~/.claude/skills` leaves every laptop slightly
  different. Here the catalog is a Git repository: `git pull && repo-template globals` makes
  machines identical, while credentials, history and caches stay local.

## How it works

```mermaid
flowchart LR
  subgraph S["Standards repository (this repo)"]
    T["Project baseline<br/>src/repo_template/templates.py"]
    K["Skill catalog<br/>.agents/skills/"]
    C["Portable settings<br/>.claude/settings.json"]
  end
  T -- "repo-template new / update" --> P1["my-service/"]
  T -- "repo-template new / update" --> P2["legacy-app/"]
  K -- "repo-template globals" --> H["~/.agents<br/>~/.claude/skills/*"]
  C -- "repo-template globals" --> H2["~/.claude/settings.json"]
  H --> A["Claude Code and Codex,<br/>in every repository"]
  H2 --> A
```

### Who owns each generated file

Every file in the project baseline has a policy that decides what `update` may do to it.

| Policy | Files | What `update` does |
| --- | --- | --- |
| **Managed** | CI workflow, Dependabot, PR template, pre-commit hook, `.editorconfig`, `.gitattributes`, `.python-version`, `CLAUDE.md` | Upgrades the file to the current standard **only if** it is unchanged since it was generated. Edited files are left alone and reported. |
| **Seed** | `README.md`, `AGENTS.md`, `CONTEXT.md`, `CHANGELOG.md`, `.env.example`, issue templates, `docs/adr/README.md`, package `__init__.py`, smoke test | Written once if missing, then the file is yours. Never touched again. |
| **Merged** | `pyproject.toml`, `.gitignore`, `.vscode/*.json` | Adds what is missing and never removes anything: dev dependencies and tool tables in `pyproject.toml`, a marked block in `.gitignore`, missing keys, extension recommendations and tasks in VS Code files. Project metadata and dependencies are not touched. |

Each generated repository commits a `.repo-template.json` manifest that records the template
version, the project variables, and a SHA-256 of every file as generated. That hash is how
`update` tells "unchanged since generation, safe to upgrade" from "you edited this, leave it".

```mermaid
flowchart TD
  A["File in the baseline"] --> B{"Exists in the repository?"}
  B -- no --> C["Create it"]
  B -- yes --> D{"Policy"}
  D -- seed --> E["Leave it: project-owned"]
  D -- merged --> F["Add missing entries only"]
  D -- managed --> G{"Matches the hash recorded<br/>when it was generated?"}
  G -- yes --> H["Upgrade to the current standard"]
  G -- no --> I["Preserve it and report it<br/>for manual review"]
```

Running `update` a second time changes nothing.

### Global linking: portable files only, never machine state

`repo-template globals`:

- links `~/.agents` → `<standards>/.agents` (Codex and the `npx skills` CLI read global skills
  from here);
- links `~/.claude/settings.json` → `<standards>/.claude/settings.json` (model, effort level,
  enabled plugins, and deny rules for reading `.env` and key files);
- creates one link per skill, `~/.claude/skills/<name>` → `<standards>/.agents/skills/<name>`;
- adds `.agents/`, `.claude/` and `.codex/` to your global Git ignore, so personal agent
  configuration never leaks into project repositories.

It never links `~/.claude` itself, so credentials, sessions, history, caches and Claude's
`synced` directory stay on the machine. Anything it replaces is first moved to
`~/.repo-template/backups/<timestamp>/`.

## Quick start

### Install (once per machine)

Keep this repository at a stable path. On a Mac, `/aiDevStandards` is the recommended
location; on the Linux workstation it lives at `/ai/Moore/repo-template`.

```bash
git clone git@github.com:bennwitt/repo-template.git /aiDevStandards
cd /aiDevStandards
uv tool install --editable .
repo-template globals --standards-root /aiDevStandards --check   # preview
repo-template globals --standards-root /aiDevStandards           # apply
```

Because the install is editable, a `git pull` updates the CLI and its templates without a
reinstall. Set `AI_DEV_STANDARDS=/aiDevStandards` in your shell profile to omit
`--standards-root`.

### Create a repository

```bash
repo-template new my-service --parent ~/code --description "Processes customer jobs."
cd ~/code/my-service
uv run pytest
```

`new` normalizes the name (`My Service` becomes the project `my-service` with package
`my_service`), refuses to write into a non-empty directory, runs `git init -b main`, points
`core.hooksPath` at `.githooks/`, and creates `uv.lock`. `--python 3.13` changes the Python
version (default `3.12`). Use `--no-git` or `--no-lock` only when another system owns those
steps.

### Bring an existing repository up to standard

```bash
repo-template check  /path/to/repo   # dry run: lists what would change, writes nothing
repo-template update /path/to/repo   # apply
```

For a repository without a manifest, `update` infers the name, description and Python version
from `pyproject.toml`. Files that already exist and differ from the standard are listed under
**Preserved for manual review**. Compare them with a freshly generated repository, merge by
hand, and run `update` again. `update` also configures the Git hook path (skip with
`--no-hooks`) and creates `uv.lock` when it is missing or refreshes it when `pyproject.toml`
changed (skip with `--no-lock`). `check` plans the same steps, including the hook path and the
lockfile, so a clean `check` means `update` has nothing to do.

### Exit codes

| Command | `0` | `1` | `2` |
| --- | --- | --- | --- |
| `new` | created | created, but a Git or uv step failed | n/a |
| `update` | applied cleanly | a Git or uv step failed | files preserved for manual review |
| `check` | current | something would change | n/a |
| `globals --check` | current | links would change | n/a |

This makes the CLI easy to script, for example `repo-template check . || echo "standards drifted"`.

## What a generated repository contains

```text
my-service/
├── AGENTS.md              # commands, layout and working agreements for any agent
├── CLAUDE.md              # "@AGENTS.md": Claude reads the same guide as Codex
├── CONTEXT.md             # domain glossary and system boundaries
├── docs/adr/              # architecture decision records
├── README.md, CHANGELOG.md
├── pyproject.toml         # uv_build, pytest, Ruff, mypy --strict
├── src/my_service/        # __init__.py, py.typed
├── tests/test_smoke.py
├── .githooks/pre-commit   # secret scan, uv lock --check, ruff, mypy, pytest
├── .github/               # CI, Dependabot (uv and Actions), PR and issue templates
├── .vscode/               # interpreter, pytest, Ruff on save, tasks
├── .env.example           # .env, *.pem and *.key are ignored
├── .ai/receipt-policy.json
└── .repo-template.json    # ownership manifest: commit it
```

## The skill catalog

Skills live in `.agents/skills/<name>/SKILL.md`. `.claude/skills/` in this repository is a mirror
of symlinks, so the same skills appear when you open this repository in Claude Code.

A skill with `disable-model-invocation: true` runs only when you type `/name`, so it costs no
context until you use it. The others are listed in every session so the agent can pick them up
on its own. Claude Code's `/skill-doctor` shows each skill's per-turn context cost and how often
it is used; run it occasionally and prune what you never use.

### Engineering workflow (mattpocock/skills)

A typical feature moves through these skills:

```mermaid
flowchart LR
  G["/grill-with-docs<br/>stress-test the idea"] --> S["/to-spec"] --> T["/to-tickets"] --> I["/implement"] --> R["code-review"]
```

| When you want to… | Use |
| --- | --- |
| Find the right skill or flow | `/ask-matt` |
| Stress-test a plan | `grilling`, `/grill-me`, `/grill-with-docs` (also writes ADRs and glossary terms) |
| Turn a discussion into work | `/to-spec`, `/to-tickets`, `/wayfinder` (work larger than one session) |
| Build | `/implement`, `/implement-spec`, `tdd`, `prototype` |
| Fix a hard bug or regression | `diagnosing-bugs` |
| Improve structure | `/improve-codebase-architecture`, `codebase-design`, `domain-modeling` |
| Review changes | `code-review` (against repository standards and against the spec) |
| Manage issues | `/triage`, `/to-questionnaire` |
| Pause and resume | `/handoff`, `/claude-handoff` |
| Write | `writing-for-agents`, `/writing-fragments`, `/writing-shape`, `/writing-beats` |
| Research, learn, reflect | `research`, `/teach`, `/loop-me`, `/retro` |
| Steps only a human can do | `wizard` |

Run `/setup-matt-pocock-skills` once in each repository. It records where issues are tracked,
the triage label names, and the domain-doc layout in `docs/agents/*.md`, which `to-spec`,
`to-tickets` and `triage` read.

### Domain and tooling packs

| Pack | Skills | Source |
| --- | --- | --- |
| LangChain, LangGraph, Deep Agents, LangSmith | `ecosystem-primer` (start here), `langchain-*`, `langgraph-*`, `deep-agents-*`, `deepagents-*-quickstart`, `managed-deep-agents`, `langsmith-online-eval-engineering`, `eval-engineering`, `swarm` | langchain-ai/langchain-skills |
| Knowledge graphs | `knowledge-graph-extraction`, `knowledge-graph-etl` (BidCore `kg` MCP server) | local |
| Gradio | `gradio`, `hf-gradio` | gradio-app |
| Agent and Git hygiene | `find-skills`, `git-guardrails-claude-code`, `resolving-merge-conflicts` | vercel-labs/skills, mattpocock/skills |
| TypeScript and course tooling | `setup-ts-deep-modules`, `migrate-to-shoehorn`, `setup-pre-commit` (Husky), `scaffold-exercises` | mattpocock/skills |

Claude Code plugins (skill-creator, GitHub, Playwright, hookify, and others) are enabled through
`.claude/settings.json` rather than vendored here.

### Add, update, or remove a skill

Because `~/.agents` points at this repository, the `npx skills` CLI installs global skills
straight into the catalog:

```bash
npx skills find changelog                                    # search https://skills.sh
npx skills add owner/repo --skill some-skill -g -a claude-code codex
ln -s ../../.agents/skills/some-skill .claude/skills/some-skill   # repository mirror
repo-template globals                                        # link it for Claude on this machine
git add .agents/skills/some-skill .claude/skills/some-skill
git commit -m "Add some-skill skill"
```

On every other machine, run `git pull && repo-template globals`. `npx skills update -g`
refreshes installed skills from their sources. To write a new skill, use the `skill-creator`
plugin, and follow `writing-for-agents`.

## Safety guarantees

- An edited file is never overwritten. It is reported for review and `update` exits with `2`.
- `update` is idempotent: a second run changes nothing.
- `check` and `globals --check` never write.
- Files are written atomically (temporary file, then rename).
- Global files are backed up before being replaced with links.
- `~/.claude` is never linked wholesale; only `settings.json` and individual skills are.
- Generated repositories ignore `.env`, `.env.*`, `*.pem`, `*.key`, `.agents/`, `.claude/` and
  `.codex/`. The pre-commit hook blocks staged private keys and AWS- or OpenAI-style keys.
- The CLI never creates GitHub repositories, pushes commits, or copies secrets.

## Current limitations

- `globals` adds and replaces links but doesn't remove links to skills deleted from the catalog.
- An invalid `--standards-root` silently falls back to `$AI_DEV_STANDARDS`, the current
  directory, or the install location.
- Dependabot doesn't see template content in `templates.py`, so version pins there (such as
  `uv_build`) can lag behind this repository's own `pyproject.toml`.
- `.agents/.skill-lock.json`, where `npx skills` records each skill's source, is ignored by Git,
  so `npx skills update` knows the sources only on the machine that installed them.
- New repositories don't yet include the `docs/agents/*.md` files the engineering skills expect;
  run `/setup-matt-pocock-skills` after `new`.
- Python/uv is the only project profile.

## Developing this repository

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run mypy src
uv run repo-template --help
```

- Template content: `src/repo_template/templates.py`, one `add()` call per file with its policy.
- File update and merge logic: `src/repo_template/scaffold.py`. Hook path and lockfile, shared
  by `new`, `update` and `check`: `src/repo_template/repository.py`. Global linking:
  `src/repo_template/standards.py`.
- When you change generated content, bump the version in `pyproject.toml` and
  `src/repo_template/__init__.py`, add a `CHANGELOG.md` entry, and add tests for any change to
  rendering, conflict handling or symlink behaviour.
- `CONTEXT.md` defines the domain terms used here: standards repository, project baseline,
  managed file, seed file, portable global and machine state.
