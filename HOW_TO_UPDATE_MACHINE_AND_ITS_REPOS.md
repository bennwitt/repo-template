# How to update a machine and its repositories

1. [Set up or update the machine](#1-set-up-or-update-the-machine): one script, on macOS or Linux.
2. [Update or adopt a repository](#2-update-or-adopt-a-repository): one question decides what
   to run.

`repo-template check` never writes anything: run it whenever you're unsure what `update` would do.

## 1. Set up or update the machine

**You need** Git, Claude Code (installed and signed in once) and Node 22 or 24 LTS. The script
installs `uv` if it's missing.

| | macOS | Linux |
| --- | --- | --- |
| Git | `xcode-select --install` | your package manager, e.g. `sudo apt install git` |
| Claude Code | `curl -fsSL https://claude.ai/install.sh \| bash`, then run `claude` once to sign in ([setup](https://docs.claude.com/en/docs/claude-code/setup)) | the same |
| Node 24 LTS | [nvm](https://github.com/nvm-sh/nvm): `nvm install 24`, or `brew install node@24` (then add `$(brew --prefix node@24)/bin` to `PATH`) | nvm: `nvm install 24` |
| Google Chrome, for the `playwright` MCP server's browser | [google.com/chrome](https://www.google.com/chrome/), or `brew install --cask google-chrome` | Google's `.deb` or `.rpm` |

Use nvm or Homebrew for Node: with the nodejs.org installer, `npm install -g` needs `sudo`.

1. **Get the script.**
   - A new machine:
     ```bash
     curl -fsSLO https://raw.githubusercontent.com/bennwitt/repo-template/main/setup-machine.sh
     ```
   - A machine already set up has it in its checkout. First, if
     `readlink ~/.claude/settings.json` prints a path ending in `/.claude/settings.json` inside
     that checkout, the machine was set up before 0.4.2: do
     [Appendix A, step 1](#appendix-a-setting-up-a-machine-by-hand) first (it pulls for you).
     Otherwise find the checkout and pull it:
     ```bash
     checkout=$(dirname "$(readlink ~/.agents)") && git -C "$checkout" pull --ff-only
     ```
     The script is then `"$checkout/setup-machine.sh"`.
2. **Run it**, and answer its questions (the defaults are safe):
   ```bash
   bash setup-machine.sh
   ```
   It asks where the standards repository goes: `~/aiDevStandards` on a new machine, otherwise
   the checkout the machine uses. Then it:
   - clones or pulls that repository, and installs the `repo-template` command;
   - writes `AI_DEV_STANDARDS` into a marked block of your shell profile (on a Mac, once you
     store a GitHub token in the Keychain ([1.1](#11-optional-tools)), also a line that reads it);
   - shows what `repo-template globals` would change (skill links, Claude Code settings, the
     global MCP servers, the Git ignore lines in the file your Git reads), and applies it when
     you say yes;
   - offers each optional tool in [1.1](#11-optional-tools), with "no" as the default.

   - **Backups:** its block in your shell profile, and the settings, MCP and ignore files
     `globals` changes, are backed up to `~/.repo-template/backups/<time>/` first. (`uv`'s own
     setup adds a `PATH` line to your shell's startup files.)
   - **When something fails:** a failed clone or install stops it with a message and exit 1. A
     failed `globals` or profile step is reported, the rest still runs, and it exits 1 at the
     end. A failed optional tool is reported with the command to run later.
   - **Again any time:** it changes only what is missing or out of date. `--yes --dir PATH`
     answers every question with its default (it installs `uv` if needed, creates the folder and
     applies `globals`, but installs no optional tool); `--help` lists the options.
3. **Check it worked.** Open a new terminal, then:
   ```bash
   bash "$AI_DEV_STANDARDS/setup-machine.sh" --check   # each part: ok, or ! and what to do
   claude mcp list                                    # playwright and huggingface: connected
   ```
   `--check` changes nothing and exits 1 while a `!` line is left (`--offline` skips asking
   GitHub whether the checkout is current). Restart Claude Code (and Codex) so they pick up the
   new settings and servers.

To do these steps by hand instead, see [Appendix A](#appendix-a-setting-up-a-machine-by-hand).

### 1.1 Optional tools

The script offers each of these, at the versions `.agents/machine-tools.json` pins: each the
newest release at least 7 days old, except `typescript-language-server` 5.3 and TypeScript 6,
held back on purpose (6 needs Node 22.22, and TypeScript 7 has no `tsserver`; see the README's
Per-machine tools). The commands below are for installing one by hand.

| Tool | For | macOS | Linux |
| --- | --- | --- | --- |
| Language servers, Playwright CLI | the `typescript-lsp` and `pyright-lsp` plugins; the `playwright-cli` skill | `npm install -g --ignore-scripts typescript-language-server@5.3.0 typescript@6.0.3 pyright@1.1.414 @playwright/cli@0.1.22`, then `playwright-cli install-browser chromium` | the same |
| Azure CLI (`az`) | the `azure` and `foundry` packs | `brew install azure-cli` | Microsoft's packages: [install the Azure CLI on Linux](https://learn.microsoft.com/cli/azure/install-azure-cli-linux) |
| Azure Developer CLI (`azd`) 1.35.0 | the same packs | from [its release](https://github.com/Azure/azure-dev/releases): `azd-darwin-arm64.zip` (Apple silicon) or `azd-darwin-amd64.zip` | from the same release: `azd-linux-amd64.tar.gz` or `azd-linux-arm64.tar.gz` |
| GitHub token | the `github` plugin | a fine-grained, read-only token in the Keychain (the script stores it and reads it from your profile) | a file only you can read, sourced by your profile (below) |
| Codex CLI | Codex | `npm install -g --ignore-scripts @openai/codex@0.161.0` | the same |

- **Azure:** after installing `az`, run `az login` and pick the subscription with
  `az account set --subscription "<name>"`. On a Mac the script installs `az` with Homebrew
  (install it first from [brew.sh](https://brew.sh)), which takes the current release: the one
  exception to the 7-day rule. It installs `azd` as `~/.local/bin/azd`, only once the
  download's SHA-256 matches the pin, then runs `azd config set auth.useAzCliAuth true`. By
  hand, compare the asset's SHA-256 (`shasum -a 256` on a Mac, `sha256sum` on Linux) with its
  `sha256` in `.agents/machine-tools.json` before you put `azd` on your `PATH`.
- **GitHub token on Linux:**
  ```bash
  install -m 600 /dev/null ~/.config/github-token        # then put this line in it:
  #   export GITHUB_PERSONAL_ACCESS_TOKEN=<your token>
  echo '[ -f ~/.config/github-token ] && . ~/.config/github-token' >> ~/.bashrc   # or ~/.zshrc
  ```
- **Codex:** after installing it, run `codex` once, then the setup script again, so Codex gets
  its MCP servers.
- **Plugins that need a sign-in:** greptile (`/greptile:login` in Claude Code) and atlassian
  (authorize it in `/mcp`).

## 2. Update or adopt a repository

Update the machine first: a repository written by a newer repo-template stops `check` and
`update` with "newer than this repo-template".

**Which kind of repository is it?**

```bash
cd /path/to/repo
grep -h '"profile"' .repo-template.json .git/repo-template.json 2>/dev/null
```

| It prints | Go to |
| --- | --- |
| `"profile": "python-uv"` or `"profile": "packs-only"` | [2.1 Update a templated repository](#21-update-a-templated-repository) |
| `"profile": "personal"` | [2.2 Update a personal repository](#22-update-a-personal-repository) |
| nothing | [2.3 Adopt a repository](#23-adopt-a-repository) |

To see which of your repositories need updating, check several at once; each gets one line
(`current`, what it would change, or `no manifest`):

```bash
repo-template check ~/code/service-a ~/code/web-b ~/code/tool-c
```

Or ask Claude Code to "update every repository on this machine": the `repo-template` skill finds
the adopted ones, checks them together, and updates each by its kind (on a branch, with a commit,
for the templated ones), then asks you about each push.

### 2.1 Update a templated repository

1. Preview: `repo-template check .` If it prints "Standards are current.", you're done.
2. Start a branch from an up-to-date `main`:
   ```bash
   git switch main && git pull && git switch -c chore/repo-template-update
   ```
3. Apply: `repo-template update .` In a terminal it shows a diff for each file that differs from
   the baseline and asks:

   | Key | Choice |
   | --- | --- |
   | `o` | use the baseline |
   | `k` | keep yours (asked again only when the baseline's version changes) |
   | `m` | merge change by change |
   | `a` | always keep yours (never managed again) |
   | `s` | skip for now |

   Exit 2 means something is still waiting: a baseline file you haven't decided (run `update`
   again in a terminal), or another `!` line, which says its own fix.
4. Check:
   - every repository: `repo-template check .` prints "Standards are current.";
   - the full baseline also: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src`.
5. Commit and push, then open a pull request:
   ```bash
   git add -A && git commit -m "chore: update repo-template" && git push -u origin HEAD
   ```

### 2.2 Update a personal repository

```bash
git status --short > /tmp/before.txt
repo-template update .
git status --short | diff /tmp/before.txt - && echo "nothing the team sees changed"
```

There is nothing to commit. To add a pack: `repo-template update . --pack <name>`. To drop one,
edit `skill_packs` in `.git/repo-template.json`, then run `update`.

### 2.3 Adopt a repository

**Choose how.** Find out who commits to it:

```bash
git log --format='%an' | sort | uniq -c | sort -rn | head
```

| The repository is… | Use | What gets committed |
| --- | --- | --- |
| also other people's (a team's) | personal | nothing |
| yours, Python with uv | the full baseline | the baseline files, `.repo-template.json`, `.mcp.json` if a pack has servers |
| yours, another stack (TypeScript, say) | packs only | `.repo-template.json`, `.mcp.json` if a pack has servers |

Pick packs from the [pack table](README.md#catalog-every-skill-where-it-applies-and-where-it-comes-from).

**Personal** (also other people's repository):

1. `git status --short > /tmp/before.txt`
2. Preview: `repo-template check . --personal --pack <name>`
3. Apply: `repo-template update . --personal --pack <name>`
4. Check: `git status --short | diff /tmp/before.txt -` prints nothing, and `claude mcp list`
   shows the packs' servers.

It refuses a subfolder (run it at the top of the checkout), a linked worktree, a sparse checkout,
and a repository that has a `.repo-template.json` of its own. To undo it: set `skill_packs` to
`[]` in `.git/repo-template.json`, run `repo-template update .`, then delete
`.git/repo-template.json` (deleting it first leaves the links, the ignore block and the servers
behind).

**The full baseline** (yours, Python with uv):

1. Look first. The baseline adds a pre-commit hook and CI that block every commit until these
   pass:
   ```bash
   uv lock --check                 # no uv.lock yet is fine: update creates it
   uvx ruff check --select E,F,I,B,UP,SIM --line-length 100 . --statistics | tail -3
   uvx ruff format --check --line-length 100 . | tail -1
   uv run --with mypy mypy --strict src | tail -1
   uv run --with pytest pytest -q | tail -1
   ```
   With hundreds of findings, clean up first, or adopt it packs-only for now.
2. Start a branch: `git switch main && git pull && git switch -c chore/adopt-repo-template`
3. Preview: `repo-template check . --pack <name>` (`--pack` is optional and repeatable).
4. Apply: `repo-template update . --pack <name>`, and decide each file that differs (the keys in
   [2.1](#21-update-a-templated-repository)).
   - **Adds:** `AGENTS.md`, `CLAUDE.md`, `GLOSSARY.md`, `docs/adr/`, the CI workflow,
     Dependabot, the PR template, the pre-commit hook (`core.hooksPath .githooks`), and
     `tests/test_smoke.py`, which expects `__version__` in `src/<package>/__init__.py`, equal to
     the project's version (`uv init --package` doesn't define it: add it, or delete the test).
   - **Merges:** `pyproject.toml` and `.gitignore`, then refreshes `uv.lock`.
   - **Leaves alone:** a tool the project already configures keeps its settings, and code in
     `src/` but not in `src/<package>/` keeps its layout.
5. Fill in the Purpose and Boundaries sections of `AGENTS.md`.
6. Check: `uv sync --dev && uv run pytest`, and `repo-template check .` prints "Standards are
   current."
7. `git add -A && git commit -m "chore: adopt repo-template" && git push -u origin HEAD`, then
   open a pull request.

**Packs only** (yours, another stack):

1. `git switch main && git pull && git switch -c chore/repo-template-packs`
2. Preview: `repo-template check . --packs-only --pack <name>`
3. Apply: `repo-template update . --packs-only --pack <name>`
4. `git add -A && git commit -m "chore: adopt repo-template skill packs" && git push -u origin HEAD`
   (the skill links are ignored, so this commits only `.repo-template.json` and any `.mcp.json`).

Later runs need no flag: `repo-template update .`

## Troubleshooting

| You see | Do |
| --- | --- |
| `newer than this repo-template` | pull the standards repository: `git -C "$(dirname "$(readlink ~/.agents)")" pull --ff-only`, then run it again |
| `Git wouldn't ignore this link` | run `repo-template globals` (it writes the ignore lines into the file Git reads), or add `.claude/`, `.agents/` and `.codex/` to the repository's `.gitignore` |
| exit 2 and `!` lines | a baseline file waiting for a decision: run `update` in a terminal; any other `!` line says its own fix (for `globals`, see the last row) |
| Claude Code asks to approve MCP servers | they're from the repository's `.mcp.json`: approve the ones you want (a personal repository never asks) |
| `playwright` isn't connected in `claude mcp list` | check `node --version` (22 or 24) and that `npx` is on the `PATH` Claude Code starts with, then restart Claude Code |
| a browser tool fails with `Chromium distribution 'chrome' is not found` | install Google Chrome (section 1) |
| Codex doesn't see a repository's servers | Codex reads `.codex/config.toml` only in a project you trust |
| the pre-commit hook blocks a commit | it runs the checks: fix what it reports |
| `globals` reports `changed on this machine; kept` or `configured by hand; kept` | yours wins; set it back to the standard's value to follow the standard again |

## Appendix A: setting up a machine by hand

What `setup-machine.sh` does, step by step. On a Mac the standards repository goes in your home
folder (`~/aiDevStandards`): macOS keeps the top of the disk read-only.

1. **A machine set up before 0.4.2:** check whether `~/.claude/settings.json` is a link into a
   standards checkout:
   ```bash
   readlink ~/.claude/settings.json    # ".../.claude/settings.json" inside a repo-template checkout
   ```
   If it is, migrate once, so this machine's settings carry over (a link into your own dotfiles
   isn't this case: skip it):
   ```bash
   link=$(readlink ~/.claude/settings.json) && cd "${link%/.claude/settings.json}" &&
     cp .claude/settings.json ~/claude-settings-before-0.4.2.json &&
     git checkout -- .claude/settings.json && git pull &&
     cp ~/claude-settings-before-0.4.2.json .claude/settings.json &&
     repo-template globals && rm .claude/settings.json
   ```
2. **Get the standards repository.**
   - A new machine:
     ```bash
     git clone https://github.com/bennwitt/repo-template.git ~/aiDevStandards
     ```
   - A checkout that exists: `checkout=$(dirname "$(readlink ~/.agents)")`, then
     `git -C "$checkout" pull --ff-only` (on `main`, with no uncommitted changes).
3. **Install the command:** `uv tool install --editable --force <checkout>`, then
   `uv tool update-shell` (puts `~/.local/bin` on `PATH`). Being editable, a later `git pull`
   updates it.
4. **Set `AI_DEV_STANDARDS`** in your shell profile (`~/.zshrc`, or `~/.bashrc` for bash on
   Linux): `export AI_DEV_STANDARDS="<checkout>"`. Then `globals` needs no `--standards-root`.
5. **Apply the globals:** `repo-template globals --check` (what would change), then
   `repo-template globals`.
   - **What it does:** links `~/.agents` and the global skills, merges the portable settings
     into `~/.claude/settings.json`, installs the global MCP servers (Claude Code: `playwright`
     and `huggingface`; Codex: those and `microsoft-learn`), and writes `.agents/`, `.claude/`,
     `.codex/`, `.playwright-cli/` and `.playwright-mcp/` into the file Git reads for ignores
     (`core.excludesFile` when set, else `$XDG_CONFIG_HOME/git/ignore`, else
     `~/.config/git/ignore`).
   - **Exit 0:** applied.
   - **Exit 2:** something on this machine was kept (a setting or MCP server you changed, a
     file it didn't create): read the `!` lines.
   - **Exit 1:** an error; fix it and run it again.
6. **The optional tools:** [1.1](#11-optional-tools).
