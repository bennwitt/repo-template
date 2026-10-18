# Changelog

## Unreleased

- The baseline adds `.githooks/pre-push`, which fills in a pull request's description after
  each push of its branch. It returns at once and works in the background: once the pushed
  commit shows in an open pull request, `claude -p`, allowed only to read (`gh pr view`,
  `gh pr diff`, `gh pr checks` and the repository's files), fills in the PR template, and
  `gh pr edit` saves it. It writes only over a description that is empty, the untouched
  template, nothing but the branch's commit messages (what `gh pr create --fill` writes), or
  its own that nobody has edited since, and rechecks just before saving; a description someone
  wrote is left alone. It skips the default branch, tags, deletions, and machines without
  `claude` or `gh`. `PR_DESCRIPTION=0` turns it off, and `.git/pr-description.log` says what it
  did. A repository gets it on its next `update`. Where a workflow of the repository's own
  already fills in descriptions, keep one of the two: delete the hook and add it to
  `project_owned`, or drop the workflow.
- The provenance test for a vendored skill without `SKILL.md` deletes the file instead of
  renaming it to `skill.md`, which a Mac's case-insensitive disk still reads as `SKILL.md`; the
  macOS job passes again.
- 34 skills from [jeffallan/claude-skills](https://github.com/jeffallan/claude-skills) (MIT,
  v0.4.20). A machine gets them on its next `globals`, and a repository a pack's skills with
  `update --pack <name>`.
  - Global: `code-documenter`, `legacy-modernizer` and `spec-miner`.
  - In existing packs: `fastapi-expert` (`fastapi`), `mcp-developer` (`mcp`),
    `playwright-expert` (`playwright`), `react-expert` and `react-native-expert` (`react`), and
    `typescript-pro` (`typescript`).
  - New packs: `api` (`api-designer`, `graphql-architect`), `atlassian` (`atlassian-mcp`; it
    needs an Atlassian MCP server you sign in to yourself, so the pack ships none), `cli`
    (`cli-developer`), `databases` (`database-optimizer`, `postgres-pro`, `sql-pro`), `golang`
    (`golang-pro`), `ml-engineering` (`fine-tuning-expert`, `ml-pipeline`, `prompt-engineer`,
    `rag-architect`), `security` (`secure-code-guardian`, `security-reviewer`), `spring-boot`
    (`spring-boot-engineer`) and `sre` (`chaos-engineer`, `monitoring-expert`,
    `sre-engineer`).
  - `dev-workflows` holds the ones that overlap global skills: `architecture-designer`,
    `code-reviewer`, `debugging-wizard`, `feature-forge`, `fullstack-guardian`, `test-master`
    and `the-fool` (against `codebase-design`, `code-review`, `diagnosing-bugs`, `to-spec`,
    `tdd` and `grilling`). Add it only where you want them as well.
  - `python-pro` isn't vendored (it's under `ignored`): it builds with Poetry and checks with
    black, where this baseline uses uv and ruff.
  - The scanner's findings in `prompt-engineer` (prompt-injection examples it teaches defenses
    with) and in `fastapi-expert`, `fullstack-guardian`, `security-reviewer` and `test-master`
    (placeholder passwords in examples) were reviewed and are recorded under `allowFindings`.

## 0.5.4 - 2026-10-14

- `setup-machine.sh` sets up a Mac or a Linux machine in one run, and runs again safely.
  - It asks where the standards repository goes (default `~/aiDevStandards`, or the checkout the
    machine already uses), clones or pulls it, installs the CLI, and writes `AI_DEV_STANDARDS` in
    a marked block of the shell profile (the one the shell reads: `ZDOTDIR`, bash's login file on
    a Mac, fish's `conf.d`).
  - It previews `globals` (a summary on a first run), applies it once you agree, and offers each
    optional tool, defaulting to no, at the versions `.agents/machine-tools.json` pins: the npm
    packages by version, with `--before` the end of the newest pin's day so their dependencies
    wait out the cooldown too, and `azd` from its GitHub release only once the download's
    SHA-256 matches. An `azd` that isn't the pinned version is replaced, and one elsewhere on
    `PATH` (Homebrew's) is named for you to remove once the pinned one is in; a checkout that
    pins no `azd` leaves it alone. Its Python one-liners run isolated (`-I -S`), from `/`, with
    no environment activated and uv reading no configuration, so nothing in the folder you run it
    from (a `json.py`, a `.python-version`, a `.venv`) decides what runs; a uv that can't run
    Python is reported, not taken for missing pins.
  - `--check` (with `--offline`) reports what is set up and what isn't, one line each, and
    changes nothing (not even Git's index); it exits 1 while something needs fixing, and goes on
    past an origin it can't reach or a tool that doesn't run (which gets its own `!` line).
  - Its block in the shell profile is backed up to `~/.repo-template/backups/` before it
    changes, and a broken marked block is left alone. A failed clone or install stops it with a
    message (exit 1); a failed `globals` or profile step is reported and the rest still runs
    (exit 1 at the end); a failed optional tool is reported with the command to run later. A
    settings link left from before 0.4.2 is migrated first, or, when a pull already removed its
    file, reported while `globals` writes fresh settings.
  - It refuses rather than guesses: no terminal without `--yes`, a folder that isn't empty or
    holds another repository, a Git that doesn't run (a new Mac's stand-in), root, or a machine
    still on the pre-0.4.2 settings link.
- `globals` writes its ignore block to the file Git reads: `core.excludesFile` (from the system
  or global config or one they include, expanded as Git expands it, asked outside any
  repository so an `includeIf` doesn't decide it), else `$XDG_CONFIG_HOME/git/ignore`, else
  `~/.config/git/ignore`; the ignore file an `includeIf` brings in for some repositories gets
  the block too, wherever the `includeIf` is. A relative `core.excludesFile` is reported instead,
  and so is a file you can't write (an error for the always-read file, a note for a conditional
  one). It writes through a link, backs the file up first, and leaves a block that lost a marker
  line, or has them out of order, alone. Before, it always wrote `~/.config/git/ignore`, which Git doesn't read when
  `core.excludesFile` names another file. The tests no longer reach a real `XDG_CONFIG_HOME` or
  system Git config.
- `.agents/machine-tools.json` pins the per-machine CLIs once (the TypeScript and Python language
  servers, the Playwright CLI and Codex from npm; `azd` from its GitHub release, with each
  platform's asset and SHA-256), each to its newest final release at least 7 days old; `below`
  holds TypeScript under 7 and `typescript-language-server` under 6, and a `pinException`
  says why a release inside its cooldown is pinned. `globals --upstream` checks them beside the
  MCP pins (finding a pinned GitHub release by its tag, however old), and compares each
  recorded `azd` digest with GitHub's.
- `globals --upgrade mcp:<name>` (or the bare name, when no vendored skill has it) re-pins an
  MCP server to its newest final release past the cooldown: its args, version and
  `publishedAt` together, a `pinException` dropped, shown and asked first, noted here.
  `--upstream`'s pin lines name the command. Skills named in the same run and not reached
  (after a quit, or with npm or PyPI out of reach) are listed as left alone.
- `repo-template --version` prints the version and the standards repository the CLI runs from,
  on one line however long the path; an unknown `--pack` lists the packs there are.
- The `repo-template` skill updates every repository on a machine: it finds the adopted ones
  (not the standards checkout), checks them together, updates each by its kind on a branch from
  an up-to-date default branch, and leaves each push to you. It chooses the
  path first (full, packs-only, or personal for a team's repository) and verifies each one its
  own way.
- CI also runs the tests on macOS, under `/bin/bash` 3.2 and BSD tools; `shellcheck` (a dev
  dependency) checks `setup-machine.sh`; the weekly catalog-drift run writes its report to the
  run's summary page, says what to do for skills, servers and tools, and replays the report
  with workflow commands off (upstream text can't forge one, `##[` included).
- `HOW_TO_UPDATE_MACHINE_AND_ITS_REPOS.md`: set up a machine in three steps (or by hand, in an
  appendix), with the prerequisites and optional tools for macOS and Linux; then one question
  decides how to update or adopt each repository. The README's Mac location is
  `~/aiDevStandards` (macOS keeps the top of the disk read-only), and its install section
  points to the script and the guide. `AGENTS.md` and `GLOSSARY.md` follow.

## 0.5.3 - 2026-10-14

- `update --personal` (and `check --personal`) adopts a repository you don't manage, such as a
  team's, for your own skill packs without changing anything anyone else sees. The manifest is
  `.git/repo-template.json`; the links it makes are listed in a repo-template block in
  `.git/info/exclude`; the packs' MCP servers go to Claude Code's local scope for that checkout
  (never `.mcp.json`) and to an ignored `.codex/config.toml` (never one of your own that Git
  doesn't ignore). Paths the repository tracks are never linked, listed or removed, a server its
  `.mcp.json` defines is left to it, and a link or Codex block Git would no longer ignore is
  taken out. Later runs follow the recorded profile; it is refused in a subfolder, in a linked
  worktree or a sparse checkout, and in a repository with its own `.repo-template.json`; any
  run in a subfolder or linked worktree of a personal checkout is refused too (unless the
  subfolder has its own manifest).
- Pack `react` no longer brings the LangChain docs servers; the `langchain` pack has them, so a
  repository with both still gets them.
- The checks of what Git ignores and tracks run without the variables that tie Git to one
  repository (`GIT_DIR`, `GIT_INDEX_FILE`...), so run from a hook they ask about the right one;
  `git -c` settings still apply.

## 0.5.2 - 2026-10-14

- Skills refreshed from upstream: `ask-matt`, `claude-handoff`, `code-review`, `diagnosing-bugs`,
  `grilling`, `handoff`, `implement`, `managed-deep-agents`, `setup-matt-pocock-skills`, `tdd`,
  `teach`, `to-tickets`, `wayfinder`, `wizard`.
- Skills removed (gone upstream): `langsmith-online-eval-engineering`, `resolving-merge-conflicts`.
- Skills added from upstream: `appinsights-instrumentation`, `azure-ai`, `azure-ai-projects-ts`,
  `azure-deploy`, `azure-diagnostics`, `azure-identity-py`, `azure-identity-ts`, `azure-prepare`,
  `azure-resource-lookup`, `azure-storage`, `azure-validate`, `docker-build-strategies`,
  `docker-compose-patterns`, `docker-destructive-guardrails`, `entra-app-registration`, `fastapi`,
  `frontend-design`, `hf-mem`, `huggingface-local-models`, `microsoft-foundry`, `model-recipes`,
  `playwright-best-practices`, `playwright-cli`, `playwright-trace`, `python-mcp-server-generator`,
  `vercel-composition-patterns`, `vercel-react-best-practices`, `vllm-bench-serve`.
- New local skill `compose-gpu-serving`: GPU services in Docker Compose (device requests,
  healthchecks for slow model loads, a shared model cache, loopback ports, uv in images).
- Pack `react`: `frontend-design` (anthropics/skills, Apache-2.0) and a `shadcn` skill derived
  from shadcn-ui/ui at `shadcn@4.21.3` (the CLI pinned, nothing run when it loads, no icon
  images), with the `shadcn` MCP server (`shadcn@4.21.3`, read-only) and the LangChain docs
  servers for `useStream` UIs. Vercel's React skills aren't vendored: vercel-labs/agent-skills
  has no license file.
- Pack `playwright`: `playwright-best-practices` (currents-dev, MIT, description overridden) and
  `playwright-trace` (microsoft/playwright v1.64.0, Apache-2.0).
- Packs `azure` (azure-prepare, -validate, -deploy, -diagnostics, -resource-lookup,
  -storage, appinsights-instrumentation, entra-app-registration, azure-identity-py and -ts) and
  `foundry` (microsoft-foundry, azure-ai, azure-ai-projects-ts), from microsoft/azure-skills and
  microsoft/skills (MIT). Long descriptions are overridden; `microsoft-foundry` runs only when
  asked (`/microsoft-foundry`), since on load it installs an azd extension, edits AGENTS.md and
  starts billable evaluations. Both packs share the `azure` MCP server: Azure MCP 3.0.0 through
  `uvx`, `--read-only`, with each pack's namespaces (no Key Vault), signing in through az
  login. 3.0.0 is under 7 days old, with a recorded `pinException`. Packs may add only
  `--namespace` (`packArgs`), so none can undo `--read-only`; `AZURE_TOKEN_CREDENTIALS` may only
  name a credential type. App Service settings are returned only after a consent prompt; the
  `foundry` and `arm` namespaces proxy Microsoft's hosted servers, whose read-only marking comes
  from those services, and `foundryextensions` can call deployed models (spending tokens).
- Pack `react` adds `vercel-react-best-practices` and `vercel-composition-patterns`
  (vercel-labs/agent-skills). That repository has no license file; its README says MIT, so the
  README is the recorded license text and a change to it is flagged for review. The React
  description is scoped to Next.js App Router and React 19.2+, and points to the rule files
  rather than the compiled AGENTS.md, which drops code in five sections.
- New derived skill `web-interface-guidelines` in pack `react`: Vercel's Web Interface
  Guidelines (vercel-labs/web-interface-guidelines, MIT) copied at a fixed commit. The upstream
  `web-design-guidelines` skill fetched them from `main` at every review, so it isn't vendored.
- Pack `local-inference`: `model-recipes` (vllm-project/vllm), `vllm-bench-serve`
  (vllm-project/vllm-skills), `hf-mem` and `huggingface-local-models` (huggingface/skills), all
  Apache-2.0, and two local skills: `local-model-serving` (vLLM, llama.cpp and Ollama on a
  workstation GPU: pinned images, parsers, Ampere quantization, co-resident memory, exposure,
  clients and Claude Code against a local model) and `muse-glimmer` (Meta Muse Glimmer on vLLM:
  sampling, reasoning strength, tool calls, LangChain, Open WebUI and Claude Code).
- Pack `vision`: local skills `opencv-python` (one headless wheel, colour order, dtypes and
  EXIF at every hand-off, video I/O, servers, tests) and `sam3` (Meta SAM 3 and 3.1: hosted,
  transformers and native paths, prompts, coordinates, GPU memory, the SAM License).
- `compose-gpu-serving`: vLLM's `--gpu-memory-utilization` default is 0.92 (v0.29 to v0.31).
- Packs `fastapi` (local `fastapi-services`: tests, lifespan, auth with PyJWT and pwdlib,
  CORS, Open WebUI tool servers, an OpenAI-compatible streaming endpoint in front of a graph),
  `mcp` (local `mcp-servers`, and `python-mcp-server-generator` from github/awesome-copilot with
  its description overridden; MCP server `fastmcp-docs`, its feedback tool denied) and
  `openwebui` (local `openwebui`: an agent as an OpenAI-compatible model, Pipes, Tools, Filters,
  tool servers, deployment; and `frontend-design`).
- Pack `foundry` adds the local `foundry-langchain` (LangChain, LangGraph and Deep Agents on
  Foundry, keyless); pack `gradio` adds `frontend-design`. The `microsoft-foundry` description
  no longer mentions agent.yaml, which the current azd agent extension refuses.
- `langgraph-decision-models` (langchain-ai/langchain-skills) is recorded as ignored: it routes
  through LangSmith Gateway or the TypeSafe API, and LangSmith is out of scope here.
- The `azure` plugin is off (the packs replace it: about 16,000 characters of descriptions in
  every session, a telemetry hook, and an MCP server that runs `@azure/mcp@latest`).
- Portable settings ask before Azure deploys, deletes and purges, role assignments, admin
  consent, credential resets, key listings, `az`/`azd` extension installs, `terraform
  apply`/`destroy` and `kubectl debug`/`delete`/`drain`.
- `globals --upgrade` accepts an empty `.gitignore` in a skill (microsoft-foundry has one).
- Portable settings ask before `playwright-cli run-code` (it runs code outside the page).
- `globals --upgrade` accepts a new source's skill whose `license` field states the license
  GitHub detects for the repository (docker/skills does), instead of refusing it.
- Codex 0.160.1 shows about 40,000 characters of skills before it truncates; a test keeps the
  global skills to half of that.
- Generated `.gitignore` ignores `.playwright-cli/`, `.playwright-mcp/`, `.auth/`,
  `test-results/`, `playwright-report/` and `blob-report/` (browser sessions, saved logins,
  traces and reports), `.azure/` (azd environment settings) and `.foundry/` (the
  microsoft-foundry skill's copies of production conversations and connection strings); the
  global excludes that `globals` writes add the two Playwright CLI folders.
- The pre-commit secret scan also stops Hugging Face tokens (`hf_…`), Meta API keys
  (`LLM|<id>|<secret>`), more private-key headers, temporary AWS keys (`ASIA…`) and more OpenAI
  and Anthropic key forms. It looks only at lines being added, so a commit that removes a key
  isn't stopped, and it reads the diff the same way whatever the user's diff settings (colour,
  external diff tools, textconv) or the file's encoding.
- `update` adds the baseline's `[build-system]` (uv_build) to a `pyproject.toml` without one when
  the code is in `src/<package>/`, unless `[tool.uv] package = false`: repositories generated
  before the baseline had it couldn't install their package, so their own tests failed.
- The pre-commit hook runs `uv lock`, Ruff, mypy and pytest without Git's repository variables
  (`git rev-parse --local-env-vars`). Git sets them for hooks, and in a worktree a test that ran
  git in a temporary folder wrote into the repository being committed instead (it happened here:
  `core.bare` and a test user landed in the shared config). The test suite strips them too.

## 0.5.1 - 2026-10-14

- `update --packs-only --pack <name>` adopts a repository that isn't Python/uv for its skill packs
  and their MCP servers alone: its manifest records the `packs-only` profile, which later `update`
  and `check` follow, and no baseline file, hook path or lockfile is written.
- `globals --upstream` checks each MCP pin against npm or PyPI: a newer final release past the
  7-day cooldown is a change, a younger one a note; a yanked pin, a wrong `publishedAt`, a pin
  inside its cooldown without a `pinException`, and an exception no longer needed are for review.
- `check` takes `--packs-only` and `--pack`, to preview an adoption. Every refusal (a Python/uv
  or foreign manifest, a newer version, a missing directory) now comes before anything is
  written, and a `.repo-template.json` with no known profile is never overwritten.

## 0.5.0 - 2026-10-14

- MCP servers: `.agents/mcp-servers.json` defines each server once (pinned `npx`/`uvx` package or
  URL, clients, denied tools, why). `globals` installs the global ones in Claude Code's user scope
  (`claude mcp add-json`) and `~/.codex/config.toml`; a pack's servers go into the repository's
  `.mcp.json` and an ignored `.codex/config.toml`. Claude Code gets `${NAME:-default}`, Codex
  literal values. Entries are owned by name and digest (in `globals-state.json` and the manifest's
  new `mcp_servers` and `mcp_kept`): an entry changed by hand is kept and reported once, and one
  removed stays removed. A denied tool is denied in both clients. The catalog accepts only `npx`
  and `uvx` commands that run their pin first, pins at least 7 days old (or with a
  `pinException`; a younger one isn't installed), and nothing that looks like a secret or a
  machine's Azure IDs. A pack may add only the flags its server lists in `packArgs`, checked
  the same way, so `--read-only` can't be undone; `--dangerously-*`, `--insecure-*` and a
  non-stdio `--transport` are refused.
  Global: `playwright` (0.0.83, isolated, headless), `huggingface`, and `microsoft-learn` for
  Codex; the `langchain` pack gets the LangChain docs and reference servers, `gradio` its docs
  server.
- The `playwright` plugin is off in the portable settings (the pinned server replaces it), and
  `mcp__*__submit_feedback` is denied.

## 0.4.3 - 2026-10-14

- Pack skills move to `.agents/packs/`, outside every folder Codex reads on its own, so Codex
  sees them only where a repository lists the pack, like Claude Code. `update` links a pack's
  skills into the repository's `.agents/skills/` (for Codex) as well as `.claude/skills/`, and
  repoints links from before the move. Integrity checks that a skill lives in `.agents/packs/`
  exactly when a pack lists it (by where its SKILL.md is, so a moved skill's leftover caches don't
  count), in every standards repository. Verified with Codex 0.160.1's `debug prompt-input`.
- `update` makes a pack link only where Git ignores it, and never replaces a link it didn't make.
  It skips a folder that isn't one (a dangling `.agents` link), resolves outside the repository,
  or is the catalog, and reports each. `globals --upgrade` refreshes or removes a skill in the
  folder it lives in.
- `globals --upstream` compares every vendored skill and license text with upstream, read-only, and
  confirms each recorded commit holds the vendored folder. `globals --upgrade [SKILL …]` refreshes
  skills, or adds one as `owner/repo@skill-or-path[#ref]`. Each is staged, verified against the
  upstream tree SHA (from the listing and from the files written), scanned with the committed
  `skill-scanner`, shown as a terminal-safe diff that names the files the scanner doesn't read (and
  new URLs, binary files and permission frontmatter), and swapped in with its records only when you
  apply it, as one journaled transaction that a failure, signal or kill rolls back. A scanner crash,
  new critical/high findings, a changed upstream license or an unrecorded skill-level license refuse
  it; moved skills are followed; nothing is committed. `npx skills` is no longer part of the catalog
  workflow. `--upstream` and `--upgrade` exit `3` when GitHub can't be reached. A weekly
  `catalog-drift.yml` runs `--upstream`.
- The README lists the per-machine tools the portable plugins and skills need (language servers,
  Playwright CLI and its browser, azd, Codex), each pinned to its newest release at least 7 days
  old, and explains the `github` plugin's token.
- Catalog integrity, checked offline by `globals --check` and the tests: every skill is recorded,
  in the lock or as a local skill in the new `.agents/skill-sources.json`, with the upstream
  commit it came from and the tree that commit was recorded for. Every vendored skill hashes to
  its lock entry (a pure-Python git tree hash over the working tree), and nothing untracked, no
  symlink and no submodule sits in it. An override may change only its own frontmatter fields,
  to exactly what it writes: its entry records the upstream text it replaced, so the rest of the
  `SKILL.md` is checked too, and `globals` marks the changed file with a comment linking the
  original. Every source and derived origin has a license record with a copyright line and
  license texts pinned to their upstream blobs; local skills are under this repository's
  license, and a vendored skill with a license of its own must record it. A SKILL.md that runs
  commands when it loads (`` !`…` ``, ```` ```! ```` blocks, or `hooks:`, found as Claude Code
  finds them, including in its argument substitution) must be allowed explicitly. A skill that
  fails any check isn't linked. This catches drift like `eval-engineering`'s five scripts,
  reformatted before the first commit and unnoticed until now; they are restored to upstream.
- `globals` reports catalog problems as errors and still finishes linking (a standards root
  without `.git` used to stop halfway). Deleting the lock or the sources file is an error, not a
  way to turn the checks off.
- The repository has an MIT `LICENSE` (verbatim, so GitHub detects it) and declares it in
  `pyproject.toml`. `THIRD_PARTY_NOTICES.md` and the README's catalog table (every skill: where
  it applies, source at its commit, license, notes) are generated by `globals` from the lock, the
  packs and the sources. The hand-kept tables they replace had drifted: `wait-what` was missing,
  and `repo-template` was credited to mattpocock/skills.
- A skill may belong to several packs. Descriptions this repository writes (overrides and local
  skills) are capped at 350 characters; four were shortened.

## 0.4.2 - 2026-10-13

- `globals` merges portable settings into a real `~/.claude/settings.json` instead of linking it
  to this repository. A link let Claude Code write `/model` and `/effort` changes from any
  machine into the shared file. The source moves to `.agents/claude-settings.json`. It has a
  `portable` part that `globals` keeps current entry by entry (a plugin switch, a permission
  rule, a hook) and a `defaults` part (model, effort, theme, notifications) that is written once
  per machine. An entry changed on the machine is kept and reported once, not overwritten.
  Values you already had, and links that repo-template didn't create, are left alone.
- **Upgrading other machines:** follow "Upgrading a machine from a linked settings file" in the
  README: save a copy of `.claude/settings.json`, `git checkout --` it (Claude Code's writes through
  the link block the pull), pull, put the copy back (Git ignores it now), run `repo-template
  globals`, then delete the copy. The migration then keeps that machine's own values and backs up
  its content. Without the copy, the dangling link is treated like a fresh machine. Until
  `globals` runs, Claude Code on that machine has no user settings.
- Portable settings changes: `mcp-server-dev` (stale against MCP spec 2026-07-28 and SDK v2),
  `mcp-apps` and `sourcegraph` are turned off; `typescript-lsp` is turned on; Azure telemetry
  opt-outs; destructive Docker commands (`prune`, `rmi`, `volume rm`, `compose down -v`) ask
  first; Playwright's `browser_run_code_unsafe` is denied; the `.env` deny rules match at any
  depth (`./**/.env`), not only the session's directory. `remoteControlAtStartup` and
  `permissions.allow` are no longer distributed: settings that widen access are chosen on each
  machine. A migrated machine that had `remoteControlAtStartup` keeps it as its own setting.
- `typescript-lsp` and `pyright-lsp` need their language servers on each machine:
  `npm i -g typescript-language-server@6.0.1 typescript` and `uv tool install pyright` (or
  `npm i -g pyright`).

## 0.4.1 - 2026-10-13

Fixes from auditing the update process:

- `check` reports the rewrite of `.repo-template.json` that `update` makes (a new template
  version, dropped or new hashes), so a clean `check` really means `update` has nothing to do.
  Before, `check` said "Standards are current." while `update` still changed the manifest.
- A manifest written by a newer repo-template stops `update` and `check` with "git pull the
  standards repository", instead of downgrading every managed file to the older baseline.
- Runtime errors (an unknown pack, an unreadable manifest, a non-empty target) print
  `repo-template: error: …` and exit 1. They used to exit 2, the code for "preserved for manual
  review", so scripts and agents went looking for files to decide.
- `globals` exits 1 when it reports an error and 2 when it preserves something, instead of 0.
- `globals` no longer picks the current directory as the standards repository just because it
  has `.agents/skills/` and `.claude/settings.json`: it uses the installed checkout, and asks for
  `--standards-root` when the current directory is a different repo-template checkout. Running
  `globals` inside a project could relink `~/.agents` and the Claude settings to that project.
- A skill pack listed in a manifest but no longer defined in `skill-packs.json` is reported, and
  its links are kept, instead of being removed silently.
- A project-owned file that the project deleted stays deleted.
- A merged file that doesn't parse (`pyproject.toml`, `.vscode/*.json`) can no longer be replaced
  by the baseline's bare template, which would have wiped the project's metadata and
  dependencies with one keypress.
- A complete VS Code JSON file keeps its own formatting instead of being rewritten with 2-space
  indentation.
- Skill overrides work on SKILL.md files with Windows line endings, and one unusable override is
  reported instead of stopping `globals`.
- `check` accepts several repositories and prints one summary line for each, with any errors on
  stderr.
- A decision made while resolving (keep, merge, use the baseline, move) records itself in the
  manifest exactly as `update` would, so a fully resolved session ends with "Standards are
  current." instead of a manifest update.
- A dev dependency with extras (`coverage[toml]`) no longer makes a valid `pyproject.toml` look
  like invalid TOML: the merge found the end of the `dev` array at the `]` inside the extras. A
  valid file whose layout the merge can't handle is now reported as such, not as invalid.
- A project-owned `AGENTS.md` or `GLOSSARY.md` that the project deleted is no longer offered a
  move from `CLAUDE.md` or `CONTEXT.md` on every run.
- An interactive `update` keeps a first-pass failure (a failed `uv lock`) in its exit code. When a
  run has both errors and preserved files, `update` and `globals` now both exit 1.
- Skill overrides keep a SKILL.md's own line endings.

## 0.4.0 - 2026-10-01

- `update` resolves discrepancies itself. In a terminal it shows a diff for each file that differs
  from the baseline and asks: use the baseline, keep yours, merge change by change, always keep
  yours, or skip. A file under an old name (`CONTEXT.md`, a `CLAUDE.md` holding the guide) can be
  moved with `git mv`, followed by a list of lines still mentioning the old name. Decisions apply
  as they are made. Without a terminal, or with `--no-input`, `update` lists the files as before.
- "Keep yours" and merged results are recorded as accepted differences in `.repo-template.json`
  (the file's hash and the baseline's), so `update` asks again only when the baseline's version
  changes. "Always keep yours" adds the file to `project_owned`.

## 0.3.1 - 2026-10-01

Found by adopting the baseline in bidcore, which it didn't generate:

- `update` added `[tool.ruff]` (line length 100) beside an existing `[tool.ruff.lint]`, which made
  90 more files fail `ruff format --check`. Tool tables are now added only for tools the project
  doesn't configure at all.
- `update` created an empty `src/<package>/`, a smoke test for it and a strict `[tool.mypy]`
  naming it, in a repository whose code sits directly in `src/`. A flat layout is now kept.
- `update` created a generic `AGENTS.md` beside a `CLAUDE.md` holding the real guide, so Codex
  read a placeholder. It now reports `CLAUDE.md` for a move into `AGENTS.md` instead.
- With no description in `pyproject.toml`, the fallback used the checkout directory's name rather
  than the project's.
- The skill receipt hook reads the older `log_path` spelling, so a policy using it no longer
  writes receipts to an unignored file.
- The `repo-template` skill covers adopting a repository: deciding each preserved managed file,
  moving `CLAUDE.md`, and repointing references after renaming `CONTEXT.md`.

## 0.3.0 - 2026-10-01

- Fix CI: `astral-sh/setup-uv` stopped publishing a floating `v10` tag, so every run failed to
  resolve it. Actions are now pinned to commit SHAs with version comments, and checkout no
  longer persists credentials. A test keeps workflow actions SHA-pinned.
- Replace the PR template with type-of-change and areas checklists, action-and-outcome
  verification steps, the quality checks, and a risk and rollback section.
- Skill packs: domain skills (`langchain`, `agent-evals`, `gradio`, `knowledge-graph`,
  `typescript`) load only in repositories that opt in with `new`/`update --pack NAME`.
- Skill overrides: `.agents/skill-overrides.json` keeps local frontmatter edits to vendored skills
  across `npx skills update`; used to narrow seven over-broad or over-long descriptions.
- `project_owned` in `.repo-template.json` lets a repository keep its own version of a managed
  file without `update` exiting `2` forever.
- Add a `repo-template` skill, and the `uv`, `ruff`, `supply-chain-risk-auditor`,
  `property-based-testing`, `github-actions-hardening`, `skill-scanner` and `pr` skills. Every
  vendored skill except the local `knowledge-graph-extraction` now has a recorded source.
- File policies move into `policies.py` behind one `decide` interface; the manifest records
  hashes only for managed files. The shared marker-block merge no longer expands backslash
  sequences in ignore rules.
- This repository passes its own `check`, enforced by a test. The baseline's smoke test now
  compares `__version__` with package metadata instead of hard-coding `0.1.0`.

## 0.2.0 - 2026-10-01

- Generate `GLOSSARY.md` (terms only) instead of `CONTEXT.md`, following the mattpocock skills'
  rename; Purpose and Boundaries move into the generated `AGENTS.md`. `update` lists an existing
  `CONTEXT.md` for a manual `git mv` instead of renaming a project-owned file, so existing
  repositories exit with `2` until they migrate.
- `check` is now a true dry run of `update`: it reports the Git hook path and `uv.lock` too, and
  accepts `--no-hooks` and `--no-lock`.
- `globals` removes links to deleted skills, keeps the `.claude/skills/` mirror in sync, and
  rejects an invalid `--standards-root` or `AI_DEV_STANDARDS`.
- Record skill receipts through Claude Code hooks for repositories with `.ai/receipt-policy.json`.
- Raise the baseline's `uv_build` pin to match this repository, and test that the two stay in
  sync.
- Commit `.agents/.skill-lock.json`, update nine mattpocock skills and `langgraph-fundamentals`,
  and remove `knowledge-graph-etl`, `swarm`, `setup-pre-commit` and `scaffold-exercises`.

## 0.1.0 - 2026-09-17

- Add safe `new`, `update`, `check`, and `globals` workflows.
- Add a Python/uv repository baseline derived from BidCore.
- Add portable Codex and Claude skill/settings synchronization.

