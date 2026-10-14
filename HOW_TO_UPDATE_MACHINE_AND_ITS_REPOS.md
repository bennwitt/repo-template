# How to update a machine and its repositories

Three jobs, in this order:

1. [Update the machine](#1-update-the-machine): bring the standards repository, the CLI, and
   the global skills, settings and MCP servers up to date.
2. [Update a repository that is already templated](#2-update-a-repository-that-is-already-templated).
3. [Template a repository that wasn't created from the template](#3-template-a-repository-that-wasnt-created-from-the-template).

The commands assume a Mac with the standards repository at `~/aiDevStandards`, named by
`$AI_DEV_STANDARDS` (on the Linux workstation it is `/ai/Moore/repo-template`). macOS doesn't let
you create a folder at the top of the disk (the system volume is read-only), so keep it in your
home folder. `check` never writes anything, so run it whenever you're unsure what `update` would
do.

## 1. Update the machine

### The quick way: one script

`setup-machine.sh` sets up a Mac or a Linux machine, the first time or any time after. Download
it, read it, then run it:

```bash
curl -fsSLO https://raw.githubusercontent.com/bennwitt/repo-template/main/setup-machine.sh
less setup-machine.sh
bash setup-machine.sh
```

It asks where the standards repository goes. The default is `~/aiDevStandards`, or, on a
machine already set up, the checkout it uses. Then it does steps 1.2 to 1.5 below:

- clone or pull the standards repository;
- install the `repo-template` command;
- show what `globals` would change, and apply it if you say yes;
- copy the Git ignore lines where Git reads them;
- offer each optional tool, with "no" as the default.

It installs `uv` if it's missing (it asks first), and it never runs as root. Run it again
whenever you like: it changes only what is missing or out of date. `--yes --dir PATH` runs it
without questions (skipping the optional tools), and `--help` lists the options.

The steps below are what it does, for reference, or to do by hand.

### 1.1 Check the prerequisites

```bash
git --version        # any recent Git (Xcode's command line tools have one)
uv --version         # https://docs.astral.sh/uv/
node --version       # 22 or 24 LTS (20 works for most things, but is past its end of life)
claude --version     # Claude Code CLI: needed to install the MCP servers
codex --version      # optional: only if you use Codex
```

On a new Mac, install what is missing:

```bash
xcode-select --install                     # Git, if `git --version` asks for it
brew install uv node@24                    # or uv's installer: https://docs.astral.sh/uv/
echo 'export PATH="$(brew --prefix node@24)/bin:$PATH"' >> ~/.zshrc   # node@24 isn't linked
uv tool update-shell                       # puts ~/.local/bin (where repo-template goes) on PATH
```

Install Claude Code and open it once (`claude`), so `~/.claude` exists. Then open a new terminal.

### 1.2 Get the latest repo-template

**First time on this machine** (no checkout yet; on a Mac, `readlink ~/.agents` prints
nothing): skip to "First time on this machine" below.

**This machine was set up before 0.4.2** if `~/.claude/settings.json` is a link:

```bash
ls -l ~/.claude/settings.json      # "-> <checkout>/.claude/settings.json" means a link
```

If it is a link, migrate once, so this machine's settings carry over:

```bash
cd "$AI_DEV_STANDARDS"                     # the checkout the link points into
cp .claude/settings.json ~/claude-settings-before-0.4.2.json   # this machine's view
git checkout -- .claude/settings.json      # changes Claude Code wrote through the link
git pull                                   # removes .claude/settings.json; the link now dangles
cp ~/claude-settings-before-0.4.2.json .claude/settings.json   # Git ignores it now
repo-template globals
rm .claude/settings.json
```

Then continue at [1.3](#13-check-your-global-git-ignore).

**Otherwise**, pull:

```bash
cd "$AI_DEV_STANDARDS"
git status                 # should be clean; commit or stash anything that isn't
git switch main
git pull
grep -m1 '^version' pyproject.toml          # 0.5.3 or later
```

The CLI is an editable install, so the pull updates it too. Check that it did:

```bash
repo-template update --help | grep -- --personal   # prints the --personal option
```

If that prints nothing, the CLI was installed another way. Install it again from the checkout:

```bash
uv tool install --editable --force "$AI_DEV_STANDARDS"
```

**First time on this machine:**

```bash
echo 'export AI_DEV_STANDARDS="$HOME/aiDevStandards"' >> ~/.zshrc && source ~/.zshrc
git clone https://github.com/bennwitt/repo-template.git "$AI_DEV_STANDARDS"
cd "$AI_DEV_STANDARDS"
uv tool install --editable .
repo-template --help                       # the CLI is on PATH
```

The repository is public, so the HTTPS clone needs no key. To push from this machine later, use
`git@github.com:bennwitt/repo-template.git` with an SSH key for that account.

On a machine set up earlier, set `AI_DEV_STANDARDS` in `~/.zshrc` the same way (to wherever
its checkout is), so `globals` never needs `--standards-root`.

### 1.3 Check your global Git ignore

`globals` adds `.agents/`, `.claude/`, `.codex/`, `.playwright-cli/` and `.playwright-mcp/` to
`~/.config/git/ignore`. Git reads that file only when `core.excludesFile` isn't set to another
one, and many Macs set it to `~/.gitignore_global`:

```bash
git config --global --get core.excludesFile
```

- **No output:** nothing to do.
- **A path:** Git reads that file instead. After step 1.4, copy the repo-template block from
  `~/.config/git/ignore` into it. Or stop using it with
  `git config --global --unset core.excludesFile`, after moving its lines into
  `~/.config/git/ignore`.

Without this, skill links in packs-only repositories show up in `git status`, and `update`
refuses to make them. Personal adoption doesn't depend on it.

### 1.4 Preview, then apply, the global standards

```bash
repo-template globals --check      # what would change; writes nothing
repo-template globals              # apply
```

The run:

- links `~/.agents` to the catalog;
- links each global skill into `~/.claude/skills/`;
- merges the portable settings into `~/.claude/settings.json`;
- installs the global MCP servers:
  - Claude Code's user scope gets `playwright` and `huggingface`;
  - Codex gets those two and `microsoft-learn`, in `~/.codex/config.toml`;
- writes the global Git ignore.

Anything it replaces goes to `~/.repo-template/backups/<timestamp>/` first.

| Exit | Meaning | What to do |
| --- | --- | --- |
| `0` | applied cleanly | nothing |
| `2` | something was kept: a setting changed on this machine, a file it didn't create | read the `!` lines; they're reported once, and you can leave them |
| `1` | an error | fix what it says and run it again |

Then check the result:

```bash
repo-template globals --check      # "Standards are current."
claude mcp list                    # playwright and huggingface show as connected
ls ~/.claude/skills | wc -l        # the global skills
```

Restart Claude Code (and Codex) so they pick up the new settings and servers.

### 1.5 Per-machine tools (as you need them)

The skills and plugins expect some CLIs on each machine. Pin each one to its newest release
at least 7 days old. These versions were current on 2026-10-13:

```bash
# language servers for the typescript-lsp and pyright-lsp plugins
npm install -g --ignore-scripts typescript-language-server@5.3.0 typescript@6.0.3 pyright@1.1.414
# Playwright CLI, in step with the playwright-cli skill, and its browser
npm install -g --ignore-scripts @playwright/cli@0.1.22
playwright-cli install-browser chromium
# only for the azure and foundry packs: sign in, then fetch the Azure MCP server once
az login
uvx --exclude-newer 2026-10-13T00:00:00Z --from msmcp-azure==3.0.0 azmcp --version
```

- **Azure Developer CLI (`azd`), for the Azure packs:**
  - download the macOS asset for your chip from its GitHub release;
  - check its SHA-256 against the release's digest, and put `azd` on your PATH;
  - run `azd config set auth.useAzCliAuth true`.
- **The `github` plugin:** set `GITHUB_PERSONAL_ACCESS_TOKEN` in the environment Claude Code
  starts in. A fine-grained, read-only token is enough. It never goes in a repository.
- **Node 20:** `typescript-language-server` 6 needs Node 22.22 or later. On Node 20, keep 5.3.

## 2. Update a repository that is already templated

Do this after updating the machine. A repository written by a newer repo-template than yours
stops `check` and `update` with "newer than this repo-template": pull the standards repository
first.

### 2.1 Find out how it was templated

```bash
cd /path/to/repo
grep '"profile"' .repo-template.json .git/repo-template.json 2>/dev/null
```

| Shows | Kind | What `update` touches |
| --- | --- | --- |
| `.repo-template.json: "profile": "python-uv"` | full baseline | baseline files, `pyproject.toml`, hook path, `uv.lock`, skill packs |
| `.repo-template.json: "profile": "packs-only"` | packs only | skill links, `.mcp.json`, the manifest |
| `.git/repo-template.json: "profile": "personal"` | personal (a repository you don't manage) | only files on your machine; nothing to commit |

### 2.2 Full baseline or packs only

```bash
git switch main && git pull
git switch -c chore/repo-template-<version>     # e.g. chore/repo-template-0.5.3
repo-template check .                           # what would change
repo-template update .                          # apply; asks about each file that differs
```

For each file that differs from the baseline, `update` shows a diff and asks:

| Key | Choice |
| --- | --- |
| `o` | use the baseline |
| `k` | keep yours (asked again only when the baseline changes) |
| `m` | merge change by change |
| `a` | always keep yours (never managed again) |
| `s` | skip for now |

Then check and commit:

```bash
repo-template check .            # "Standards are current."
uv run pytest && uv run ruff check . && uv run mypy src      # full baseline only
git add -A && git commit -m "chore: update to repo-template <version>"
git push -u origin HEAD          # then open a pull request
```

Exit `2` from `update` means files were kept for you to decide. Run `update` again in a terminal
to decide them, or leave them for later.

### 2.3 Personal

```bash
git status --short > /tmp/before.txt
repo-template update .
git status --short | diff /tmp/before.txt - && echo "nothing the team sees changed"
```

There is nothing to commit. To add a pack, run `repo-template update . --pack <name>`. To drop
one, edit `skill_packs` in `.git/repo-template.json` and run `update`.

## 3. Template a repository that wasn't created from the template

### 3.1 Choose how to adopt it

| The repository is… | Use | What gets committed |
| --- | --- | --- |
| yours, Python with uv (or ready to move to uv) | full baseline: `update` | baseline files, `.repo-template.json`, `.mcp.json` if a pack has servers |
| yours, but not Python/uv (TypeScript, say) | `update --packs-only --pack …` | `.repo-template.json`, `.mcp.json` |
| someone else's, or a team's you're one member of | `update --personal --pack …` | nothing |

Whose is it? `git log --format='%an' | sort | uniq -c | sort -rn | head` shows who commits.
When others do, use `--personal`: your skills and servers stay yours, and teammates are never
asked to approve your MCP servers.

To pick packs, list them:

```bash
python3 -c "import json; [print(f'{k:16} {v[\"description\"]}') for k, v in json.load(open('$AI_DEV_STANDARDS/.agents/skill-packs.json')).items()]"
```

### 3.2 Full baseline (yours, Python/uv)

The baseline adds a pre-commit hook and CI that run `ruff`, `mypy` and `pytest`. On a codebase
that doesn't pass them, every commit is blocked. Look first:

```bash
cd /path/to/repo
uvx ruff check --select E,F,I,B,UP,SIM --line-length 100 . --statistics | tail -3
uv run pytest -q | tail -1
```

If there are hundreds of findings, clean up first, or adopt it packs-only for now (3.3).

```bash
git switch main && git pull
git switch -c chore/adopt-repo-template
repo-template check . --pack <name>            # preview: every file it would create or change
repo-template update . --pack <name>           # apply; decide each file that differs
```

`--pack` is optional, and you can repeat it. It infers the name, description and Python version
from `pyproject.toml`.

- **What it adds:** `AGENTS.md`, `CLAUDE.md`, `GLOSSARY.md`, `docs/adr/`, the CI workflow,
  Dependabot, the PR template and the pre-commit hook (`core.hooksPath .githooks`).
- **What it merges:** `pyproject.toml` and `.gitignore`; it then refreshes `uv.lock`.
- **What it leaves alone:** a tool the project already configures keeps its settings, and code
  in `src/` but not in `src/<package>/` keeps its layout.

Then:

```bash
uv sync --dev && uv run pytest
repo-template check .                           # "Standards are current."
git add -A && git commit -m "chore: adopt repo-template"
git push -u origin HEAD                         # then open a pull request
```

Fill in the Purpose and Boundaries sections of the new `AGENTS.md` before the pull request.

### 3.3 Packs only (yours, not Python/uv)

```bash
git switch -c chore/repo-template-packs
repo-template check . --packs-only --pack react --pack playwright
repo-template update . --packs-only --pack react --pack playwright
git add .repo-template.json .mcp.json
git commit -m "chore: adopt repo-template skill packs"
```

Later runs need no flag: `repo-template update .`

### 3.4 Personal (someone else's repository)

```bash
git status --short > /tmp/before.txt
repo-template check . --personal --pack react --pack playwright   # preview
repo-template update . --personal --pack react --pack playwright
git status --short | diff /tmp/before.txt - && echo "nothing the team sees changed"
claude mcp list                    # the packs' servers, local to this checkout
```

It refuses:

- a subfolder (run it at the top of the checkout);
- a linked worktree;
- a sparse checkout;
- a repository that already has a `.repo-template.json`.

To undo it:

1. Set `skill_packs` to `[]` in `.git/repo-template.json`.
2. Run `repo-template update .`.
3. Delete `.git/repo-template.json`.

## Troubleshooting

| You see | Do |
| --- | --- |
| `was written by repo-template X, newer than this repo-template` | `cd "$AI_DEV_STANDARDS" && git pull`, then run it again |
| `Git wouldn't ignore this link` | fix the global ignore (1.3), or add `.claude/` and `.agents/` to the repository's `.gitignore` |
| exit `2` and `! …` lines | files kept for you to decide: run `update` in a terminal |
| Claude Code asks to approve MCP servers | the repository's `.mcp.json`; approve the ones you want (personal adoption never asks) |
| Codex doesn't see a repository's servers | Codex reads `.codex/config.toml` only in a project you trust |
| a commit is blocked by the pre-commit hook | it runs the checks; fix what it reports (never skip it with `--no-verify` without a reason) |
| `globals` says a setting was `changed on this machine; kept` | yours wins; set it back to the value in `.agents/claude-settings.json` to follow the standard again |
