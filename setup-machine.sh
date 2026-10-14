#!/usr/bin/env bash
# Set up a Mac or a Linux machine for repo-template: clone (or update) the standards repository,
# install the repo-template command, link the global skills, settings and MCP servers, and, if
# you want them, the tools the skills use. Safe to run again: each step checks first and changes
# only what is missing or out of date. Nothing is installed without asking, unless you pass
# --yes: then each question takes its default (uv is installed if missing, the folder created and
# globals applied; the optional tools, whose default is no, are skipped).
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
STAMP=$(date +%Y%m%d-%H%M%S)

dir=""
assume_yes=0
run_globals=1
run_tools=1
status=0 # 1 once a step reported an error; the run goes on, and exits 1 at the end

usage() { sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; }

say() { printf '\n==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
warn() { printf '    ! %s\n' "$*" >&2; }
die() {
  printf '\nsetup-machine: %s\n' "$*" >&2
  exit 1
}
have() { command -v "$1" >/dev/null 2>&1; }

# clean_path TEXT: a typed, pasted or Finder-dragged folder, without surrounding spaces or
# quotes and without the backslashes a drag puts before spaces; ~ means the home folder
clean_path() {
  local path=$1
  path="${path#"${path%%[![:space:]]*}"}"
  path="${path%"${path##*[![:space:]]}"}"
  case "$path" in
    \"*\") path=${path#\"} && path=${path%\"} ;;
    \'*\') path=${path#\'} && path=${path%\'} ;;
  esac
  path=$(printf '%s' "$path" | sed 's/\\\(.\)/\1/g')
  case "$path" in
    \~) path=$HOME ;;
    \~/*) path="$HOME/${path#\~/}" ;;
  esac
  case "$path" in /*) ;; *) path="$PWD/$path" ;; esac
  while [ "$path" != / ] && [ "${path%/}" != "$path" ]; do path=${path%/}; done
  printf '%s\n' "$path"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dir)
      [ $# -ge 2 ] || die "--dir needs a path"
      dir=$2
      shift 2
      ;;
    --dir=*)
      dir=${1#--dir=}
      shift
      ;;
    -y | --yes)
      assume_yes=1
      shift
      ;;
    --no-globals)
      run_globals=0
      shift
      ;;
    --no-tools)
      run_tools=0
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1 (see --help)" >&2
      exit 2
      ;;
  esac
done

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

# optional WHAT COMMAND...: run an optional step; a failure is reported, never fatal
optional() {
  local what=$1
  shift
  if ! "$@"; then warn "$what didn't work; you can run it later: $*"; fi
}

is_standards() { [ -f "$1/pyproject.toml" ] && grep -q '^name = "repo-template"' "$1/pyproject.toml"; }
version_of() { sed -n 's/^version = "\(.*\)"$/\1/p' "$1/pyproject.toml" | head -n 1; }

# put_block FILE START END BLOCK [HEADING]: FILE with its START..END lines replaced by BLOCK, or
# BLOCK added at the end. A file whose markers aren't one START before one END is left alone. The
# file is backed up before it changes, and written in place (through a symlink, keeping the
# target); HEADING is shown only then. Succeeds when the file holds BLOCK afterwards.
put_block() {
  local file=$1 start=$2 end=$3 block=$4 heading=${5:-} starts ends first last new
  starts=$(grep -cxF -- "$start" "$file" 2>/dev/null || true)
  ends=$(grep -cxF -- "$end" "$file" 2>/dev/null || true)
  starts=${starts:-0}
  ends=${ends:-0}
  if [ "$starts" = 1 ] && [ "$ends" = 1 ]; then
    first=$(grep -nxF -- "$start" "$file" | cut -d: -f1)
    last=$(grep -nxF -- "$end" "$file" | cut -d: -f1)
  fi
  if [ "$starts$ends" != 00 ] && { [ "$starts$ends" != 11 ] || [ "$first" -gt "$last" ]; }; then
    warn "$file has a broken repo-template block (a '$start' line without its end line, or the other way round); fix it by hand, then run this again"
    return 1
  fi
  new=$(mktemp)
  if [ "$starts" = 1 ]; then
    BLOCK=$block awk -v s="$start" -v e="$end" \
      '$0 == s { print ENVIRON["BLOCK"]; skip = 1; next } $0 == e { skip = 0; next } !skip' \
      "$file" >"$new"
  else
    {
      if [ -s "$file" ]; then
        cat "$file"
        [ -z "$(tail -c 1 "$file")" ] || printf '\n'
        printf '\n'
      fi
      printf '%s\n' "$block"
    } >"$new"
  fi
  if [ -f "$file" ] && cmp -s "$new" "$file"; then
    rm -f "$new"
    return 0
  fi
  if [ -n "$heading" ]; then say "$heading"; fi
  if [ -f "$file" ]; then
    mkdir -p "$HOME/.repo-template/backups/$STAMP"
    cp "$file" "$HOME/.repo-template/backups/$STAMP/$(basename "$file")"
  else
    mkdir -p "$(dirname "$file")"
  fi
  cat "$new" >"$file"
  rm -f "$new"
  note "updated $file"
}

case "$(uname -s)" in
  Darwin) os=mac ;;
  Linux) os=linux ;;
  *) die "only macOS and Linux are supported" ;;
esac
[ "$(id -u)" != 0 ] || die "run it as yourself, not as root: everything goes in your home folder"

# 1. What the machine has.

say "Checking this machine ($os)"
if ! git --version >/dev/null 2>&1; then # a new Mac's /usr/bin/git is only a stand-in
  if [ "$os" = mac ]; then note "Apple's command line tools include Git: run xcode-select --install, then this again"; fi
  die "git is needed"
fi
note "git: $(git --version)"
if ! have uv; then
  if confirm "uv (the Python package manager repo-template runs with) isn't installed. Install it?" y; then
    if [ "$os" = mac ] && have brew; then
      brew install uv || true
    else
      curl -LsSf https://astral.sh/uv/install.sh | sh || true
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

# A machine set up before 0.4.2 has ~/.claude/settings.json linked into a standards checkout.
if [ -L "$HOME/.claude/settings.json" ]; then
  linked=$(readlink "$HOME/.claude/settings.json")
  case "$linked" in
    */.claude/settings.json)
      if is_standards "${linked%/.claude/settings.json}"; then
        die "$HOME/.claude/settings.json is a link into ${linked%/.claude/settings.json} (a machine set up before 0.4.2). Follow 'Upgrading a machine from a linked settings file' in that repository's README.md first, then run this again"
      fi
      ;;
  esac
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
dir=$(clean_path "$dir")
case "$dir" in
  *[\"\$\`\\]*) die "choose a folder whose path has no quotes, \$, backticks or backslashes: $dir" ;;
esac
if [ -n "$existing" ] && [ "$existing" != "$dir" ] && is_standards "$existing"; then
  warn "$HOME/.agents points into $existing; this run moves the machine to $dir"
fi

say "Standards repository: $dir"
if [ -d "$dir/.git" ]; then
  is_standards "$dir" || die "$dir is a Git repository, but not repo-template; choose another folder"
  was=$(version_of "$dir")
  branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD)
  if [ -n "$(git -C "$dir" status --porcelain --untracked-files=no)" ]; then
    warn "it has uncommitted changes, so it wasn't pulled; commit or stash them, then run this again"
  elif [ "$branch" != main ]; then
    warn "it is on branch $branch, not main, so it wasn't pulled"
  elif git -C "$dir" pull --ff-only --quiet; then
    note "up to date with origin/main: $(git -C "$dir" log -1 --format='%h %s')"
    if [ "$(version_of "$dir")" != "$was" ]; then
      note "repo-template $was -> $(version_of "$dir"): what changed is in $dir/CHANGELOG.md"
      note "to see which repositories to update: repo-template check <repo> <repo> ..."
    fi
  else
    warn "git pull failed (above); continuing with what is there"
  fi
elif [ -e "$dir" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then
  die "$dir exists and isn't empty; choose another folder"
else
  confirm "Create $dir and clone the standards repository there?" y || die "stopped; nothing was changed"
  if ! mkdir -p "$dir" 2>/dev/null; then
    hint=""
    if [ "$os" = mac ]; then hint=" (macOS keeps the top of the disk read-only: choose a folder in your home folder)"; fi
    die "can't create $dir$hint"
  fi
  git clone --quiet "$REPO_URL" "$dir"
  note "cloned $REPO_URL"
fi
note "repo-template $(version_of "$dir")"

# 3. The repo-template command.

say "Installing the repo-template command"
uv tool install --quiet --editable --force "$dir"
bin=$(uv tool dir --bin)
"$bin/repo-template" --help >/dev/null || die "repo-template didn't install"
note "$bin/repo-template (an editable install: a git pull updates it)"
case ":$PATH:" in
  *":$bin:"*) ;;
  *)
    if uv tool update-shell >/dev/null 2>&1; then
      note "$bin is on PATH in new terminals (uv tool update-shell)"
    else
      warn "couldn't add $bin to PATH; add it to your shell profile: export PATH=\"$bin:\$PATH\""
    fi
    ;;
esac
export AI_DEV_STANDARDS="$dir"

# 4. The shell profile: AI_DEV_STANDARDS, and on a Mac the Keychain's GitHub token if it has one.
# Written before anything optional, so a failure later can't leave it out.

shell_name=$(basename "${SHELL:-}")
profile_file() {
  case "$shell_name" in
    zsh) printf '%s\n' "${ZDOTDIR:-$HOME}/.zshrc" ;;
    bash)
      if [ "$os" = linux ]; then
        printf '%s\n' "$HOME/.bashrc"
        return
      fi
      # a login shell reads only the first of these: never create one that hides another
      for candidate in .bash_profile .bash_login .profile; do
        if [ -e "$HOME/$candidate" ]; then
          printf '%s\n' "$HOME/$candidate"
          return
        fi
      done
      printf '%s\n' "$HOME/.bash_profile"
      ;;
    fish) printf '%s\n' "${XDG_CONFIG_HOME:-$HOME/.config}/fish/conf.d/repo-template.fish" ;;
    *) printf '\n' ;;
  esac
}
token_in_keychain() { [ "$os" = mac ] && security find-generic-password -a "$USER" -s github-pat >/dev/null 2>&1; }
write_profile() {
  local profile block
  profile=$(profile_file)
  if [ "$shell_name" = fish ]; then
    block="$PROFILE_START
set -gx AI_DEV_STANDARDS \"$dir\""
    if token_in_keychain; then
      block="$block
set -gx GITHUB_PERSONAL_ACCESS_TOKEN (security find-generic-password -a \$USER -s github-pat -w 2>/dev/null)"
    fi
  else
    block="$PROFILE_START
export AI_DEV_STANDARDS=\"$dir\""
    if token_in_keychain; then
      block="$block
export GITHUB_PERSONAL_ACCESS_TOKEN=\"\$(security find-generic-password -a \"\$USER\" -s github-pat -w 2>/dev/null)\""
    fi
  fi
  block="$block
$PROFILE_END"
  if [ -z "$profile" ]; then
    warn "don't know where ${shell_name:-your shell} reads its settings; add this to its startup file:"
    printf '%s\n' "$block"
    return
  fi
  put_block "$profile" "$PROFILE_START" "$PROFILE_END" "$block" "Shell profile" || status=1
}
write_profile

# 5. Global skills, settings and MCP servers.

if [ "$run_globals" = 1 ]; then
  say "Global skills, settings and MCP servers (repo-template globals)"
  output=$(mktemp)
  set +e
  "$bin/repo-template" globals --standards-root "$dir" --check >"$output" 2>&1
  checked=$?
  set -e
  if [ "$checked" = 0 ]; then
    note "already current"
  else
    if [ -f "$HOME/.repo-template/globals-state.json" ]; then
      sed 's/^/    /' "$output" # a machine set up before: the list is short
    else
      count() { grep -c "^  $1 " "$output" || true; }
      note "a first run: $(count '[+]') to create, $(count '~') to update, $(count -) to remove, $(count !) to review"
      note "anything it replaces is backed up to ~/.repo-template/backups/ first"
      if confirm "Show the full list?" n; then sed 's/^/    /' "$output"; fi
    fi
    if confirm "Apply these changes?" y; then
      set +e
      "$bin/repo-template" globals --standards-root "$dir" >"$output" 2>&1
      applied=$?
      set -e
      grep -E '^  [!x] ' "$output" | sed 's/^/  /' || true # only what needs your attention
      case "$applied" in
        0) note "applied" ;;
        2) note "applied; the ! lines above are kept for you to review (reported once)" ;;
        *)
          warn "repo-template globals reported errors (the x lines above); fix them, then run this again"
          status=1
          ;;
      esac
    else
      note "skipped: run 'repo-template globals' when you're ready"
    fi
  fi
  rm -f "$output"
fi

# globals writes the personal ignores to ~/.config/git/ignore. Git reads the file core.excludesFile
# names (in an included config file too), or $XDG_CONFIG_HOME/git/ignore: keep a copy there.
written="$HOME/.config/git/ignore"
reads=$(git config --global --includes --get core.excludesFile 2>/dev/null || true)
reads=${reads:-${XDG_CONFIG_HOME:-$HOME/.config}/git/ignore}
case "$reads" in \~/*) reads="$HOME/${reads#\~/}" ;; esac
if [ "$reads" != "$written" ] && grep -qxF "$IGNORE_START" "$written" 2>/dev/null; then
  ignores=$(sed -n "/^$IGNORE_START\$/,/^$IGNORE_END\$/p" "$written")
  if grep -qxF "$IGNORE_START" "$reads" 2>/dev/null \
    || confirm "Git reads ignores from $reads, not $written: copy repo-template's lines there?" y; then
    put_block "$reads" "$IGNORE_START" "$IGNORE_END" "$ignores" "Git ignores" || status=1
  fi
fi

# 6. Optional tools.

if [ "$run_tools" = 1 ]; then
  say "Optional tools (each asks first; the default is no)"
  if have npm && confirm "Install the TypeScript and Python language servers and the Playwright CLI (global npm packages)?" n; then
    optional "Installing the npm packages" npm install -g --ignore-scripts \
      typescript-language-server@5.3.0 typescript@6.0.3 pyright@1.1.414 @playwright/cli@0.1.22
    if have playwright-cli; then optional "Downloading Chromium" playwright-cli install-browser chromium; fi
  fi
  if confirm "Set up the Azure CLI and azd, for the azure and foundry packs?" n; then
    if [ "$os" = mac ] && have brew; then
      have az || optional "Installing the Azure CLI" brew install azure-cli
      have azd || { optional "Adding azd's Homebrew tap" brew tap azure/azd && optional "Installing azd" brew install azd; }
    elif ! have az || ! have azd; then
      note "Install the Azure CLI and azd: see 'Per-machine tools' in $dir/README.md"
    fi
    if have az; then
      az account show >/dev/null 2>&1 || optional "az login" az login
      note "choose your subscription with: az account set --subscription \"<name>\""
    fi
    if have azd; then optional "azd's sign-in setting" azd config set auth.useAzCliAuth true; fi
    pinned=$(uv run --no-project --quiet python -c \
      'import json, sys; p = json.load(open(sys.argv[1]))["servers"]["azure"]["pin"]; print(p["package"] + "==" + p["version"])' \
      "$dir/.agents/mcp-servers.json" 2>/dev/null || true)
    if [ -n "$pinned" ]; then
      note "fetching the Azure MCP server ($pinned) once, so its first start doesn't time out"
      optional "Fetching $pinned" uvx --quiet --from "$pinned" azmcp --version
    fi
  fi
  if [ "$os" = mac ] && confirm "Store a GitHub token in the Keychain for Claude Code's github plugin?" n; then
    note "Create a fine-grained, read-only token on github.com (Settings > Developer settings), then paste it when asked"
    optional "Storing the token" security add-generic-password -U -a "$USER" -s github-pat -w
    write_profile # now with the line that reads the token
  elif [ "$os" = linux ]; then
    note "github plugin: export GITHUB_PERSONAL_ACCESS_TOKEN from a file only you can read (chmod 600), sourced by your shell profile; never in a repository"
  fi
  note "Codex (optional): npm install -g @openai/codex@<a release at least 7 days old>"
fi

say "Done"
if [ "$status" != 0 ]; then warn "some steps reported problems (above); fix them, then run this again"; fi
note "Open a new terminal, then restart Claude Code and Codex"
note "Check the MCP servers: claude mcp list   (playwright and huggingface, connected)"
note "Your repositories: $dir/HOW_TO_UPDATE_MACHINE_AND_ITS_REPOS.md, sections 2 and 3"
exit "$status"
