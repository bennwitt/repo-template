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
| Node 24 LTS | the installer from [nodejs.org](https://nodejs.org), or `brew install node@24` (then add `$(brew --prefix node@24)/bin` to `PATH`) | [nvm](https://github.com/nvm-sh/nvm): `nvm install 24` |
| Google Chrome, for the `playwright` MCP server | [google.com/chrome](https://www.google.com/chrome/), or `brew install --cask google-chrome` | Google's `.deb` or `.rpm` |

1. **Get the script.**
   - A new machine:
     ```bash
     curl -fsSLO https://raw.githubusercontent.com/bennwitt/repo-template/main/setup-machine.sh
     ```
   - A machine already set up has it in its checkout. Find the checkout and pull it:
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
     global MCP servers, the Git ignore), and applies it when you say yes;
   - copies the Git ignore lines to the file your Git actually reads, if that's another one;
   - offers each optional tool in [1.1](#11-optional-tools), with "no" as the default.

   Every file it changes is backed up to `~/.repo-template/backups/<time>/` first. A step that
   fails is reported, the rest still runs, and the script exits 1. Run it again any time: it
   changes only what is missing or out of date. `--yes --dir PATH` answers every question with
   its default (so it installs `uv` if needed, creates the folder and applies `globals`, but no
   optional tools); `--help` lists the options.
3. **Check it worked.** Open a new terminal, then:
   ```bash
   repo-template --help           # the command is on PATH
   claude mcp list                # playwright and huggingface: connected
   ```
   Restart Claude Code (and Codex) so they pick up the new settings and servers.

To do these steps by hand instead, see [Appendix A](#appendix-a-setting-up-a-machine-by-hand).

### 1.1 Optional tools

The script offers each of these. Versions are the newest releases at least 7 days old on
2026-10-13.

| Tool | For | macOS | Linux |
| --- | --- | --- | --- |
| Language servers, Playwright CLI | the `typescript-lsp` and `pyright-lsp` plugins; the `playwright-cli` skill | `npm install -g --ignore-scripts typescript-language-server@5.3.0 typescript@6.0.3 pyright@1.1.414 @playwright/cli@0.1.22`, then `playwright-cli install-browser chromium` | the same |
| Azure CLI (`az`) | the `azure` and `foundry` packs | `brew install azure-cli` | Microsoft's packages: [install the Azure CLI on Linux](https://learn.microsoft.com/cli/azure/install-azure-cli-linux) |
| Azure Developer CLI (`azd`) 1.35.0 | the same packs | from [its release](https://github.com/Azure/azure-dev/releases): `azd-darwin-arm64.zip` (Apple silicon) or `azd-darwin-amd64.zip` | from the same release: `azd-linux-amd64.tar.gz` or `azd-linux-arm64.tar.gz` |
| GitHub token | the `github` plugin | a fine-grained, read-only token in the Keychain (the script stores it and reads it from your profile) | a file only you can read, sourced by your profile (below) |
| Codex CLI | Codex | `npm install -g @openai/codex@<version>` | the same |

- **Azure:** after installing `az`, run `az login` and pick the subscription with
  `az account set --subscription "<name>"`. For `azd`, check the asset's SHA-256 against the
  release's digest (`shasum -a 256` on a Mac, `sha256sum` on Linux), put `azd` on your `PATH`,
  then run `azd config set auth.useAzCliAuth true`. On a Mac the script installs both with
  Homebrew, which takes the current release: the one exception to the 7-day rule.
- **GitHub token on Linux:**
  ```bash
  install -m 600 /dev/null ~/.config/github-token        # then put this line in it:
  #   export GITHUB_PERSONAL_ACCESS_TOKEN=<your token>
  echo '[ -f ~/.config/github-token ] && . ~/.config/github-token' >> ~/.bashrc   # or ~/.zshrc
  ```
- **Codex:** pick a release at least 7 days old: `npm view @openai/codex time --json | tail -5`.
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

### 2.1 Update a templated repository

1. Start a branch from an up-to-date `main`:
   ```bash
   git switch main && git pull && git switch -c chore/repo-template-update
   ```
2. Preview: `repo-template check .`
3. Apply: `repo-template update .` In a terminal it shows a diff for each file that differs from
   the baseline and asks:

   | Key | Choice |
   | --- | --- |
   | `o` | use the baseline |
   | `k` | keep yours (asked again only when the baseline's version changes) |
   | `m` | merge change by change |
   | `a` | always keep yours (never managed again) |
   | `s` | skip for now |

   Exit 2 means files are still waiting for a decision: run it again until it exits 0.
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
   uv lock --check
   uvx ruff check --select E,F,I,B,UP,SIM --line-length 100 . --statistics | tail -3
   uvx ruff format --check --line-length 100 . | tail -1
   uv run --with mypy mypy --strict src | tail -1
   uv run pytest -q | tail -1
   ```
   With hundreds of findings, clean up first, or adopt it packs-only for now.
2. Start a branch: `git switch main && git pull && git switch -c chore/adopt-repo-template`
3. Preview: `repo-template check . --pack <name>` (`--pack` is optional and repeatable).
4. Apply: `repo-template update . --pack <name>`, and decide each file that differs (the keys in
   [2.1](#21-update-a-templated-repository)).
   - **Adds:** `AGENTS.md`, `CLAUDE.md`, `GLOSSARY.md`, `docs/adr/`, the CI workflow,
     Dependabot, the PR template and the pre-commit hook (`core.hooksPath .githooks`).
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
| `Git wouldn't ignore this link` | run `setup-machine.sh` again (it copies the ignore lines to the file Git reads), or add `.claude/` and `.agents/` to the repository's `.gitignore` |
| exit 2 and `!` lines | files or entries kept for you to decide: run `update` in a terminal |
| Claude Code asks to approve MCP servers | they're from the repository's `.mcp.json`: approve the ones you want (a personal repository never asks) |
| `playwright` isn't connected in `claude mcp list` | install Google Chrome (section 1), then restart Claude Code |
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
     and `huggingface`; Codex: those and `microsoft-learn`), and writes the Git ignore.
   - **Exit 0:** applied.
   - **Exit 2:** something on this machine was kept (a setting or MCP server you changed, a
     file it didn't create): read the `!` lines.
   - **Exit 1:** an error; fix it and run it again.
6. **Make Git read the ignore lines.** `globals` writes `.agents/`, `.claude/`, `.codex/`,
   `.playwright-cli/` and `.playwright-mcp/` to `~/.config/git/ignore`. Git reads another file
   when `core.excludesFile` names one, or when `XDG_CONFIG_HOME` is set:
   ```bash
   git config --global --includes --get core.excludesFile; echo "${XDG_CONFIG_HOME:-}"
   ```
   If the first prints a path, Git reads that file; if it prints nothing and the second prints a
   folder other than `~/.config`, Git reads `<that folder>/git/ignore`. Copy the
   `# >>> repo-template personal AI directories` block from `~/.config/git/ignore` into that
   file. Without it, `update` reports a packs-only repository's skill links as "Git wouldn't
   ignore this link" and doesn't make them.
