#!/usr/bin/env bash
# Set up a Mac or a Linux machine for repo-template: clone (or update) the standards repository,
# install the repo-template command, link the global skills, settings and MCP servers, and, if
# you want them, the tools the skills use. Safe to run again: each step checks first and changes
# only what is missing or out of date. Nothing is installed without asking.
#
# Usage:
#   bash setup-machine.sh                        asks where the standards repository goes
#   bash setup-machine.sh --dir PATH --yes       no questions (optional tools are skipped)
#   bash setup-machine.sh --no-globals           everything but `repo-template globals`
#   bash setup-machine.sh --no-tools             skip the optional tools
#
# On a new machine, download it, read it, then run it:
#   curl -fsSLO https://raw.githubusercontent.com/bennwitt/repo-template/main/setup-machine.sh
#   less setup-machine.sh
#   bash setup-machine.sh

set -euo pipefail

REPO_URL="${REPO_TEMPLATE_URL:-https://github.com/bennwitt/repo-template.git}"
DEFAULT_DIR="$HOME/aiDevStandards"
PROFILE_START="# >>> repo-template (setup-machine.sh) >>>"
PROFILE_END="# <<< repo-template (setup-machine.sh) <<<"
IGNORE_START="# >>> repo-template personal AI directories"
IGNORE_END="# <<< repo-template personal AI directories"

dir=""
assume_yes=0
run_globals=1
run_tools=1

usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) [ $# -ge 2 ] || { echo "--dir needs a path" >&2; exit 2; }; dir=$2; shift 2 ;;
    --dir=*) dir=${1#--dir=}; shift ;;
    -y|--yes) assume_yes=1; shift ;;
    --no-globals) run_globals=0; shift ;;
    --no-tools) run_tools=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done

say() { printf '\n==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
warn() { printf '    ! %s\n' "$*" >&2; }
die() { printf '\nsetup-machine: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

tty_ok=0
if { : </dev/tty; } 2>/dev/null; then tty_ok=1; fi
if [ "$assume_yes" = 0 ] && [ "$tty_ok" = 0 ]; then
  die "no terminal to ask in: run it with --yes (and --dir PATH) instead"
fi

# ask QUESTION DEFAULT: the answer, or DEFAULT for an empty answer (and with --yes)
ask() {
  local answer=""
  if [ "$assume_yes" = 1 ]; then
    printf '%s\n' "$2"
    return
  fi
  [ "$tty_ok" = 1 ] || die "no terminal to ask in: run it with --yes (and --dir PATH) instead"
  printf '%s [%s]: ' "$1" "$2" >/dev/tty
  IFS= read -r answer </dev/tty || answer=""
  printf '%s\n' "${answer:-$2}"
}

# confirm QUESTION DEFAULT(y|n): succeeds for yes
confirm() {
  case "$(ask "$1" "$2")" in
    [Yy] | [Yy][Ee][Ss]) return 0 ;;
    *) return 1 ;;
  esac
}

is_standards() { [ -f "$1/pyproject.toml" ] && grep -q '^name = "repo-template"' "$1/pyproject.toml"; }

case "$(uname -s)" in
  Darwin) os=mac ;;
  Linux) os=linux ;;
  *) die "only macOS and Linux are supported" ;;
esac
[ "$(id -u)" != 0 ] || die "run it as yourself, not as root: everything goes in your home folder"

# 1. What the machine has.

say "Checking this machine ($os)"
if ! have git; then
  [ "$os" = mac ] && note "Apple's command line tools include Git: xcode-select --install"
  die "git is needed"
fi
note "git: $(git --version)"
if ! have uv; then
  if confirm "uv (the Python package manager repo-template runs with) isn't installed. Install it?" y; then
    if [ "$os" = mac ] && have brew; then
      brew install uv
    else
      curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
    PATH="$HOME/.local/bin:$PATH"
  fi
  have uv || die "uv is needed: https://docs.astral.sh/uv/getting-started/installation/"
fi
note "uv: $(uv --version)"
if have node; then
  node_version=$(node --version)
  note "node: $node_version"
  node_major=${node_version#v}
  node_major=${node_major%%.*}
  case "$node_major" in
    '' | *[!0-9]*) ;;
    *) [ "$node_major" -ge 20 ] || warn "Node $node_version is too old for the MCP servers started with npx: install Node 22 or 24 LTS" ;;
  esac
else
  warn "Node isn't installed: MCP servers started with npx (playwright, shadcn) won't run until it is (Node 22 or 24 LTS)"
fi
if have claude; then
  note "claude: $(claude --version 2>/dev/null | head -n 1)"
else
  warn "Claude Code's CLI (claude) isn't on PATH: its MCP servers are skipped; run this again once it is"
fi
if have codex; then note "codex: $(codex --version 2>/dev/null | head -n 1)"; else note "codex: not installed (optional)"; fi

if [ -L "$HOME/.claude/settings.json" ]; then
  die "$HOME/.claude/settings.json is a link (a machine set up before 0.4.2). Follow 'Upgrading a machine from a linked settings file' in the standards repository's README.md first, then run this again"
fi

# 2. Where the standards repository lives.

existing=""
if [ -L "$HOME/.agents" ]; then
  existing=$(readlink "$HOME/.agents")
  existing=${existing%/.agents}
elif [ -n "${AI_DEV_STANDARDS:-}" ]; then
  existing=$AI_DEV_STANDARDS
fi
if [ -z "$dir" ]; then
  default=$DEFAULT_DIR
  if [ -n "$existing" ] && is_standards "$existing"; then
    note "This machine already uses the standards repository at $existing"
    default=$existing
  fi
  dir=$(ask "Where should the standards repository live?" "$default")
fi
case "$dir" in
  \~) dir=$HOME ;;
  \~/*) dir="$HOME/${dir#\~/}" ;;
esac
case "$dir" in /*) ;; *) dir="$PWD/$dir" ;; esac
while [ "$dir" != / ] && [ "${dir%/}" != "$dir" ]; do dir=${dir%/}; done
if [ -n "$existing" ] && [ "$existing" != "$dir" ] && is_standards "$existing"; then
  warn "$HOME/.agents points into $existing; this run moves the machine to $dir"
fi

say "Standards repository: $dir"
if [ -d "$dir/.git" ]; then
  is_standards "$dir" || die "$dir is a Git repository, but not repo-template; choose another folder"
  branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD)
  if [ -n "$(git -C "$dir" status --porcelain --untracked-files=no)" ]; then
    warn "it has uncommitted changes, so it wasn't pulled; commit or stash them, then run this again"
  elif [ "$branch" != main ]; then
    warn "it is on branch $branch, not main, so it wasn't pulled"
  else
    git -C "$dir" pull --ff-only --quiet || warn "git pull failed (above); continuing with what is there"
    note "up to date with origin/main: $(git -C "$dir" log -1 --format='%h %s')"
  fi
elif [ -e "$dir" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then
  die "$dir exists and isn't empty; choose another folder"
else
  if ! mkdir -p "$dir" 2>/dev/null; then
    hint=""
    [ "$os" = mac ] && hint=" (macOS keeps the top of the disk read-only: choose a folder in your home folder)"
    die "can't create $dir$hint"
  fi
  git clone --quiet "$REPO_URL" "$dir"
  note "cloned $REPO_URL"
fi
note "repo-template $(sed -n 's/^version = "\(.*\)"$/\1/p' "$dir/pyproject.toml" | head -n 1)"

# 3. The repo-template command.

say "Installing the repo-template command"
uv tool install --quiet --editable --force "$dir"
bin=$(uv tool dir --bin)
"$bin/repo-template" --help >/dev/null || die "repo-template didn't install"
note "$bin/repo-template (an editable install: a git pull updates it)"
case ":$PATH:" in
  *":$bin:"*) ;;
  *)
    uv tool update-shell >/dev/null 2>&1 || true
    note "$bin is on PATH in new terminals (uv tool update-shell)"
    ;;
esac
export AI_DEV_STANDARDS="$dir"

# 4. Global skills, settings and MCP servers.

if [ "$run_globals" = 1 ]; then
  say "Global skills, settings and MCP servers: what would change"
  set +e
  "$bin/repo-template" globals --standards-root "$dir" --check
  checked=$?
  set -e
  if [ "$checked" = 0 ]; then
    note "already current"
  elif confirm "Apply these changes?" y; then
    set +e
    "$bin/repo-template" globals --standards-root "$dir"
    applied=$?
    set -e
    case "$applied" in
      0) note "applied" ;;
      2) note "applied; the ! lines above are kept for you to review (reported once)" ;;
      *) die "repo-template globals reported errors (above); fix them, then run this again" ;;
    esac
  else
    note "skipped: run 'repo-template globals' when you're ready"
  fi

  # globals writes the personal ignores to ~/.config/git/ignore; Git reads another file when
  # core.excludesFile names one
  excludes=$(git config --global --get core.excludesFile || true)
  case "$excludes" in \~/*) excludes="$HOME/${excludes#\~/}" ;; esac
  written="$HOME/.config/git/ignore"
  if [ -n "$excludes" ] && [ "$excludes" != "$written" ] && grep -qF "$IGNORE_START" "$written" 2>/dev/null \
    && ! grep -qF "$IGNORE_START" "$excludes" 2>/dev/null; then
    warn "Git reads $excludes for ignores (core.excludesFile), not $written where globals writes them"
    if confirm "Add repo-template's ignore lines to $excludes?" y; then
      { printf '\n'; sed -n "/^$IGNORE_START\$/,/^$IGNORE_END\$/p" "$written"; } >>"$excludes"
      note "added (a later change to those lines has to be copied there by hand)"
    fi
  fi
fi

# 5. Optional tools.

if [ "$run_tools" = 1 ]; then
  say "Optional tools (each asks first; the default is no)"
  if have npm && confirm "Install the TypeScript and Python language servers and the Playwright CLI (global npm packages)?" n; then
    npm install -g --ignore-scripts typescript-language-server@5.3.0 typescript@6.0.3 pyright@1.1.414 @playwright/cli@0.1.22
    playwright-cli install-browser chromium || warn "the Chromium download failed; run 'playwright-cli install-browser chromium' later"
  fi
  if confirm "Set up the Azure CLI and azd, for the azure and foundry packs?" n; then
    if [ "$os" = mac ] && have brew; then
      have az || brew install azure-cli
      have azd || { brew tap azure/azd && brew install azd; }
    elif ! have az || ! have azd; then
      note "Install the Azure CLI and azd: see 'Per-machine tools' in $dir/README.md"
    fi
    if have az; then
      az account show >/dev/null 2>&1 || az login
      note "choose your subscription with: az account set --subscription \"<name>\""
    fi
    if have azd; then azd config set auth.useAzCliAuth true; fi
    pinned=$(uv run --no-project --quiet python -c \
      'import json, sys; p = json.load(open(sys.argv[1]))["servers"]["azure"]["pin"]; print(p["package"] + "==" + p["version"])' \
      "$dir/.agents/mcp-servers.json" 2>/dev/null || true)
    if [ -n "$pinned" ]; then
      note "fetching the Azure MCP server ($pinned) once, so its first start doesn't time out"
      uvx --quiet --from "$pinned" azmcp --version >/dev/null || warn "couldn't fetch $pinned; it downloads on first use instead"
    fi
  fi
  if [ "$os" = mac ] && confirm "Store a GitHub token in the Keychain for Claude Code's github plugin?" n; then
    note "Create a fine-grained, read-only token on github.com (Settings > Developer settings), then paste it when asked"
    security add-generic-password -U -a "$USER" -s github-pat -w
  elif [ "$os" = linux ]; then
    note "github plugin: export GITHUB_PERSONAL_ACCESS_TOKEN from a file only you can read (chmod 600), sourced by your shell profile; never in a repository"
  fi
  note "Codex (optional): npm install -g @openai/codex@<a release at least 7 days old>"
fi

# 6. The shell profile: AI_DEV_STANDARDS, and the Keychain token when there is one.

case "$(basename "${SHELL:-}")" in
  zsh) profile=$HOME/.zshrc ;;
  bash) if [ "$os" = mac ]; then profile=$HOME/.bash_profile; else profile=$HOME/.bashrc; fi ;;
  *) profile=$HOME/.profile ;;
esac
block="$PROFILE_START
export AI_DEV_STANDARDS=\"$dir\""
if [ "$os" = mac ] && security find-generic-password -a "$USER" -s github-pat >/dev/null 2>&1; then
  block="$block
export GITHUB_PERSONAL_ACCESS_TOKEN=\"\$(security find-generic-password -a \"\$USER\" -s github-pat -w 2>/dev/null)\""
fi
block="$block
$PROFILE_END"
touch "$profile"
current=$(sed -n "/^$PROFILE_START\$/,/^$PROFILE_END\$/p" "$profile")
if [ "$current" != "$block" ]; then
  kept=$(mktemp)
  awk -v s="$PROFILE_START" -v e="$PROFILE_END" '$0 == s { skip = 1; next } $0 == e { skip = 0; next } !skip' \
    "$profile" >"$kept"
  { cat "$kept"; [ -s "$kept" ] && printf '\n'; printf '%s\n' "$block"; } >"$profile"
  rm -f "$kept"
  say "Shell profile"
  note "set AI_DEV_STANDARDS in $profile"
fi

say "Done"
note "Open a new terminal (or run: source $profile), then restart Claude Code and Codex"
note "Check the MCP servers: claude mcp list   (playwright and huggingface, connected)"
note "Your repositories: $dir/HOW_TO_UPDATE_MACHINE_AND_ITS_REPOS.md, sections 2 and 3"
