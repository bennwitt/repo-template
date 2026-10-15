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
#   bash setup-machine.sh --check [--offline]    report what is set up and what isn't; changes
#                                                nothing (--offline skips asking GitHub)
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
STAMP=$(date +%Y%m%d-%H%M%S)

dir=""
assume_yes=0
run_globals=1
run_tools=1
check_only=0
offline=0
status=0 # 1 once a step reported an error; the run goes on, and exits 1 at the end

usage() { sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; }

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
    --check)
      check_only=1
      shift
      ;;
    --offline)
      offline=1
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
if [ "$check_only" = 0 ] && [ "$assume_yes" = 0 ] && [ "$tty_ok" = 0 ]; then
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
case "$(uname -m)" in
  x86_64 | amd64) arch=amd64 ;;
  arm64 | aarch64) arch=arm64 ;;
  *) arch=$(uname -m) ;;
esac
if [ "$os" = mac ]; then platform="darwin-$arch"; else platform="linux-$arch"; fi

# uv_python ARG...: Python through uv, isolated from the folder you run this in: from /, with no
# environment activated (nor its bin/ on PATH), so no .venv or .python-version decides the
# interpreter; reading no uv configuration; never downloading one; and with -I -S, importing
# nothing from that folder and running no sitecustomize. UV_PYTHON, your own choice, is kept.
uv_python() {
  (
    set -f
    kept="" old_ifs=$IFS
    IFS=:
    for part in $PATH; do
      case "$part" in
        "${VIRTUAL_ENV:-/-}/bin" | "${CONDA_PREFIX:-/-}/bin") ;;
        *) kept="${kept:+$kept:}$part" ;;
      esac
    done
    IFS=$old_ifs
    unset VIRTUAL_ENV CONDA_PREFIX
    cd / && PATH=$kept uv run --no-project --no-config --no-python-downloads --quiet python -I -S "$@"
  )
}

# pins_readable CHECKOUT: uv can run Python and read the checkout's machine-tools.json
pins_readable() {
  uv_python -c 'import json, sys; json.load(open(sys.argv[1]))["tools"]' \
    "$1/.agents/machine-tools.json" >/dev/null 2>&1
}

# pin CHECKOUT KIND NAME...: from the checkout's .agents/machine-tools.json, by KIND:
#   npm      npm install's arguments for these npm tools: --before the end of the day the newest
#            of them was published (UTC), so their dependencies wait out the cooldown too, then
#            each package@version
#   asset    a GitHub tool's "file sha256 url" for this platform
#   version  the version pinned
pin() {
  local checkout=$1 kind=$2
  shift 2
  uv_python -c '
import json, sys
from datetime import datetime, timedelta, timezone
tools = json.load(open(sys.argv[1]))["tools"]
kind, platform, picked = sys.argv[2], sys.argv[3], [tools[name] for name in sys.argv[4:]]
if kind == "version":
    print(picked[0]["version"])
elif kind == "asset":
    tool = picked[0]
    asset = tool["assets"][platform]
    tag = tool["tag"].replace("{version}", tool["version"])
    print(asset["file"], asset["sha256"],
          "https://github.com/" + tool["package"] + "/releases/download/" + tag + "/" + asset["file"])
else:
    if not picked or any(tool["registry"] != "npm" for tool in picked):
        sys.exit("not npm tools")
    day = max(datetime.fromisoformat(tool["publishedAt"].replace("Z", "+00:00"))
              .astimezone(timezone.utc).date() for tool in picked)
    print("--before=" + (day + timedelta(days=1)).isoformat() + "T00:00:00Z")
    for tool in picked:
        print(tool["package"] + "@" + tool["version"])
' "$checkout/.agents/machine-tools.json" "$kind" "$platform" "$@"
}

# physical PATH: the folder's path with every link resolved, as `globals` records it
physical() { (cd -P -- "$1" 2>/dev/null && pwd -P); }

# azd_version: the first line `azd version` prints, without azd's update check or telemetry
azd_version() { AZD_SKIP_UPDATE_CHECK=1 AZURE_DEV_COLLECT_TELEMETRY=no azd version 2>/dev/null | head -n 1; }

# names_version TEXT VERSION: TEXT names VERSION as a word ("azd version 1.2.3 (commit ...)")
names_version() {
  case "$1" in
    *" $2 "* | *" $2") return 0 ;;
    *) return 1 ;;
  esac
}

# install_azd: azd at its pinned release, as ~/.local/bin/azd, once the download's SHA-256
# matches the pin. On a failure it says why, installs nothing, and returns 1.
install_azd() {
  local info file sha url work got binary
  info=$(pin "$dir" asset azd 2>/dev/null) || {
    warn "no azd is pinned for $platform"
    return 1
  }
  read -r file sha url <<<"$info"
  work=$(mktemp -d) || return 1
  if ! curl -fsSL -o "$work/$file" "$url"; then
    warn "couldn't download $url"
    rm -rf "$work"
    return 1
  fi
  if have sha256sum; then got=$(sha256sum "$work/$file" | cut -d' ' -f1); else got=$(shasum -a 256 "$work/$file" | cut -d' ' -f1); fi
  if [ -z "$sha" ] || [ "$got" != "$sha" ]; then
    warn "$file has SHA-256 $got, not the pinned $sha"
    rm -rf "$work"
    return 1
  fi
  binary="$work/unpacked/${file%%.*}"
  if ! mkdir -p "$work/unpacked" "$HOME/.local/bin"; then
    rm -rf "$work"
    return 1
  fi
  case "$file" in
    *.zip) unzip -q "$work/$file" -d "$work/unpacked" || binary="" ;;
    *) tar -xzf "$work/$file" -C "$work/unpacked" || binary="" ;;
  esac
  if [ -z "$binary" ] || [ ! -f "$binary" ]; then
    warn "$file holds no ${file%%.*}"
    rm -rf "$work"
    return 1
  fi
  if ! install -m 755 "$binary" "$HOME/.local/bin/azd"; then
    rm -rf "$work"
    return 1
  fi
  rm -rf "$work"
  note "installed azd ($file, SHA-256 checked) as ~/.local/bin/azd"
}

# check_machine: what is set up and what isn't, one line each; changes nothing. Exit 1 on a problem.
problems=0
ok() { printf '    ok  %s\n' "$*"; }
bad() {
  printf '    !   %s\n' "$*"
  problems=$((problems + 1))
}
check_machine() {
  local version major checkout branch remote local_main tools_file pins_ok state name want got
  say "Checking this machine ($os, $platform); nothing is changed"
  if git --version >/dev/null 2>&1; then ok "$(git --version)"; else bad "git doesn't run"; fi
  if ! have uv; then
    bad "uv isn't installed"
  elif version=$(uv --version 2>/dev/null) && [ -n "$version" ]; then
    ok "$version"
  else
    bad "uv is on PATH, but 'uv --version' fails"
  fi
  if have node; then
    version=$(node --version 2>/dev/null) || version=""
    major=${version#v}
    major=${major%%.*}
    case "$major" in
      '' | *[!0-9]*) bad "node ${version:-on PATH}: its version can't be read" ;;
      *)
        if [ "$major" -ge 22 ]; then
          ok "node $version"
        elif [ "$major" -ge 20 ]; then
          bad "node $version: past its end of life; install 22 or 24 LTS"
        else
          bad "node $version: too old for the MCP servers; install 22 or 24 LTS"
        fi
        ;;
    esac
  else
    bad "node isn't installed: the MCP servers started with npx need it"
  fi
  if ! have claude; then
    bad "claude isn't on PATH"
  elif version=$(claude --version 2>/dev/null) && [ -n "$version" ]; then
    ok "claude $(printf '%s\n' "$version" | head -n 1)"
  else
    bad "claude is on PATH, but 'claude --version' fails"
  fi
  checkout=""
  if [ -L "$HOME/.agents" ]; then
    checkout=$(readlink "$HOME/.agents")
    checkout=${checkout%/.agents}
  fi
  if [ -z "$checkout" ] || ! is_standards "$checkout"; then
    bad "$HOME/.agents isn't a link into a standards repository: run this script without --check"
  else
    ok "standards repository $checkout (repo-template $(version_of "$checkout"))"
    if ! branch=$(git -C "$checkout" rev-parse --abbrev-ref HEAD 2>/dev/null); then
      bad "git can't read it: 'git -C $checkout status' says why"
    else
      if [ "$branch" != main ]; then bad "it is on branch $branch, not main"; fi
      if [ -n "$(git --no-optional-locks -C "$checkout" status --porcelain --untracked-files=no 2>/dev/null)" ]; then bad "it has uncommitted changes"; fi
      if [ "$offline" = 0 ]; then
        remote=$(git -C "$checkout" ls-remote origin refs/heads/main 2>/dev/null | cut -f1) || remote=""
        local_main=$(git -C "$checkout" rev-parse --verify -q refs/heads/main 2>/dev/null) || local_main=""
        if [ -z "$remote" ]; then
          bad "its origin couldn't be reached (--offline skips this)"
        elif [ -z "$local_main" ]; then
          bad "it has no main branch: git -C $checkout switch main"
        elif [ "$remote" = "$local_main" ]; then
          ok "its main is up to date with GitHub's"
        elif git -C "$checkout" merge-base --is-ancestor "$remote" "$local_main" 2>/dev/null; then
          bad "its main has commits GitHub's doesn't: push them, or move them to a branch"
        else
          bad "GitHub's main has moved on: run this script, or git pull"
        fi
      fi
    fi
    if have repo-template && repo-template --version 2>/dev/null | grep -qF "($checkout)"; then
      ok "repo-template on PATH runs from it"
    else
      bad "repo-template on PATH doesn't run from it: run this script without --check"
    fi
    if [ -n "${AI_DEV_STANDARDS:-}" ] && [ "$(physical "$AI_DEV_STANDARDS")" = "$(physical "$checkout")" ]; then
      ok "AI_DEV_STANDARDS is set"
    else
      bad "AI_DEV_STANDARDS isn't $checkout in this shell: open a new terminal"
    fi
    if have repo-template && repo-template globals --check --standards-root "$checkout" >/dev/null 2>&1; then
      ok "globals: current (skills, settings, MCP servers, Git ignore)"
    else
      bad "globals has changes to make: 'repo-template globals --check' lists them"
    fi
    tools_file="$checkout/.agents/machine-tools.json"
    pins_ok=0
    if [ ! -f "$tools_file" ]; then
      note "this checkout has no .agents/machine-tools.json: the tools aren't checked"
    elif have uv && pins_readable "$checkout"; then
      pins_ok=1
    else
      bad "uv can't run Python to read $tools_file ('uv run python' fails), so the tools aren't checked"
    fi
    if [ "$pins_ok" = 1 ] && have npm; then
      while read -r state name want got; do
        case "$state" in
          ok) ok "$name $want" ;;
          missing) note "$name: not installed (optional; this script offers $want)" ;;
          unreadable) bad "'npm ls -g' fails, so the npm tools can't be checked" ;;
          *) bad "$name $got: the pin is $want (run this script and answer yes to install it)" ;;
        esac
      done < <(uv_python -c '
import json, subprocess, sys
pins = json.load(open(sys.argv[1]))["tools"]
listed = subprocess.run(["npm", "ls", "-g", "--depth=0", "--json"], capture_output=True, text=True)
try:  # a tree, even with an "error" beside it (a problem in it); or an "error" object alone
    tree = json.loads(listed.stdout)
    error = tree.get("error") or {}
    if "dependencies" in tree:
        have = {k: v.get("version") for k, v in tree["dependencies"].items()}
    elif error.get("code") == "ENOENT" or not (error or listed.returncode):
        have = {}  # ENOENT: a global folder with nothing installed in it yet
    else:
        raise ValueError(error)
except (ValueError, AttributeError, TypeError):
    print("unreadable - - -")
    sys.exit()
for name, tool in sorted(pins.items()):
    if tool["registry"] == "npm":
        got = have.get(tool["package"])
        state = "ok" if got == tool["version"] else ("missing" if got is None else "other")
        print(state, name, tool["version"], got or "-")
' "$tools_file" 2>/dev/null)
    elif ! have npm; then
      note "npm isn't installed (it comes with Node), so the npm tools aren't checked"
    fi
    if have azd && [ "$pins_ok" = 1 ]; then
      want=$(pin "$checkout" version azd 2>/dev/null) || want=""
      got=$(azd_version) || got=""
      if [ -z "$want" ]; then
        note "azd: ${got:-version unreadable} (no pin to compare with)"
      elif names_version "$got" "$want"; then
        ok "azd $want"
      elif [ "$(command -v azd)" = "$HOME/.local/bin/azd" ]; then
        bad "azd: '$got', not the pinned $want: run this script and answer yes to Azure"
      else
        bad "$(command -v azd) is '$got', not the pinned azd $want: remove it (Homebrew: brew uninstall azd), then run this script and answer yes to Azure"
      fi
    elif ! have azd; then
      note "azd: not installed (optional; for the azure and foundry packs)"
    fi
  fi
  if [ -n "${GITHUB_PERSONAL_ACCESS_TOKEN:-}" ]; then
    ok "GITHUB_PERSONAL_ACCESS_TOKEN is set (the github plugin)"
  else
    note "GITHUB_PERSONAL_ACCESS_TOKEN isn't set: the github plugin won't connect (optional)"
  fi
  note "the MCP servers: run 'claude mcp list' (it starts each one, so it isn't run here)"
  if [ "$problems" = 0 ]; then
    say "All set"
    exit 0
  fi
  say "$problems to fix (the ! lines)"
  exit 1
}
if [ "$check_only" = 1 ]; then check_machine; fi

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
    *)
      if [ "$node_major" -lt 20 ]; then
        warn "Node $node_version is too old for the MCP servers started with npx: install Node 22 or 24 LTS"
      elif [ "$node_major" -lt 22 ]; then
        warn "Node $node_version is past its end of life: move to Node 22 or 24 LTS when you can"
      fi
      ;;
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

# A machine set up before 0.4.2 has ~/.claude/settings.json linked into a standards checkout. While
# the file is there, migrate first (the guide's Appendix A, step 1); once a pull has removed it, the
# link dangles, and globals writes fresh settings in its place.
GUIDE="https://github.com/bennwitt/repo-template/blob/main/HOW_TO_UPDATE_MACHINE_AND_ITS_REPOS.md"
if [ -L "$HOME/.claude/settings.json" ]; then
  linked=$(readlink "$HOME/.claude/settings.json")
  case "$linked" in
    */.claude/settings.json)
      if is_standards "${linked%/.claude/settings.json}"; then
        if [ -e "$HOME/.claude/settings.json" ]; then
          die "$HOME/.claude/settings.json is a link into ${linked%/.claude/settings.json} (a machine set up before 0.4.2): migrate it first, as $GUIDE#appendix-a-setting-up-a-machine-by-hand step 1 says, then run this again"
        fi
        warn "$HOME/.claude/settings.json is a link left from before 0.4.2, and its file is gone (a pull removed it): globals writes fresh settings in its place; your old ones are in Git: git -C ${linked%/.claude/settings.json} show HEAD@{1}:.claude/settings.json"
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
# plain_path PATH: refuse a path the shell profile couldn't hold as it is
plain_path() {
  case "$1" in
    *[\"\$\`\\]*) die "choose a folder whose path has no quotes, \$, backticks or backslashes: $1" ;;
  esac
}
dir=$(clean_path "$dir")
plain_path "$dir"
if [ -d "$dir" ]; then # with its links resolved, as globals records it
  resolved=$(physical "$dir") || die "can't open $dir"
  dir=$resolved
  plain_path "$dir"
fi
if [ -n "$existing" ] && [ -d "$existing" ]; then existing=$(physical "$existing") || existing=""; fi
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
  git clone --quiet "$REPO_URL" "$dir" || die "couldn't clone $REPO_URL (the error is above)"
  note "cloned $REPO_URL"
  resolved=$(physical "$dir") || die "can't open $dir"
  dir=$resolved
  plain_path "$dir"
fi
note "repo-template $(version_of "$dir")"

# 3. The repo-template command.

say "Installing the repo-template command"
uv tool install --quiet --editable --force "$dir" || die "couldn't install repo-template (the error is above)"
bin=$(uv tool dir --bin) || die "uv can't say where it installs commands"

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

# 6. Optional tools, at the versions .agents/machine-tools.json pins.

if [ "$run_tools" = 1 ]; then
  say "Optional tools (each asks first; the default is no; the versions are pinned in .agents/machine-tools.json)"
  if ! pins_readable "$dir"; then
    warn "uv can't run Python to read $dir/.agents/machine-tools.json ('uv run python' fails): the pinned tools can't be installed"
  fi
  if have npm && confirm "Install the TypeScript and Python language servers and the Playwright CLI (global npm packages)?" n; then
    if packages=$(pin "$dir" npm typescript-language-server typescript pyright playwright-cli); then
      # shellcheck disable=SC2086 # one argument per word
      optional "Installing the npm packages" npm install -g --ignore-scripts $packages
      if have playwright-cli; then optional "Downloading Chromium" playwright-cli install-browser chromium; fi
    else
      warn "their pins couldn't be read from $dir/.agents/machine-tools.json (above): not installed"
    fi
  elif ! have npm; then
    note "npm isn't installed (it comes with Node): the language servers and Codex need it"
  fi
  if have npm && confirm "Install the Codex CLI (a global npm package)?" n; then
    if packages=$(pin "$dir" npm codex); then
      # shellcheck disable=SC2086 # one argument per word
      optional "Installing Codex" npm install -g --ignore-scripts $packages
      note "run codex once, then this script again, so Codex gets its MCP servers"
    else
      warn "Codex's pin couldn't be read from $dir/.agents/machine-tools.json (above): not installed"
    fi
  fi
  if confirm "Set up the Azure CLI and azd, for the azure and foundry packs?" n; then
    if ! have az; then
      if [ "$os" = mac ] && have brew; then # Homebrew's current release: the one exception to the 7-day rule
        optional "Installing the Azure CLI" brew install azure-cli
      else
        note "Install the Azure CLI: see section 1.1 of $dir/HOW_TO_UPDATE_MACHINE_AND_ITS_REPOS.md (on a Mac, install Homebrew first: https://brew.sh)"
      fi
    fi
    want=$(pin "$dir" version azd 2>/dev/null) || want=""
    if [ -z "$want" ] && pins_readable "$dir"; then
      note "this checkout pins no azd (pull it, then run this again): azd left as it is"
    elif [ -z "$want" ]; then
      note "azd's pin couldn't be read (above): azd left as it is"
    elif ! { have azd && names_version "$(azd_version)" "$want"; }; then
      if install_azd; then
        found=$(command -v azd || true) # on the PATH you had: is ours the one that runs?
        if [ -n "$found" ] && [ "$found" != "$HOME/.local/bin/azd" ]; then
          warn "$found is another azd ('$(azd_version)'): remove it (Homebrew: brew uninstall azd), so the pinned one in ~/.local/bin runs"
        fi
      else
        warn "azd wasn't installed (the reason is above): run this script again and answer yes to Azure, or install it by hand (section 1.1 of $dir/HOW_TO_UPDATE_MACHINE_AND_ITS_REPOS.md)"
      fi
    fi
    PATH="$HOME/.local/bin:$PATH"
    if have az; then
      az account show >/dev/null 2>&1 || optional "az login" az login
      note "choose your subscription with: az account set --subscription \"<name>\""
    fi
    if have azd; then optional "azd's sign-in setting" azd config set auth.useAzCliAuth true; fi
    azure_mcp=$(uv_python -c '
import json, sys
from datetime import datetime, timedelta, timezone
pin = json.load(open(sys.argv[1]))["servers"]["azure"]["pin"]
day = datetime.fromisoformat(pin["publishedAt"].replace("Z", "+00:00")).astimezone(timezone.utc).date()
print((day + timedelta(days=1)).isoformat() + "T00:00:00Z", pin["package"] + "==" + pin["version"])
' "$dir/.agents/mcp-servers.json" 2>/dev/null) || azure_mcp=""
    if [ -n "$azure_mcp" ]; then # as the server runs: its dependencies wait out the cooldown too
      read -r cutoff package <<<"$azure_mcp"
      note "fetching the Azure MCP server ($package) once, so its first start doesn't time out"
      optional "Fetching $package" uvx --quiet --exclude-newer "$cutoff" --from "$package" azmcp --version
    fi
  fi
  if [ "$os" = mac ] && confirm "Store a GitHub token in the Keychain for Claude Code's github plugin?" n; then
    note "Create a fine-grained, read-only token on github.com (Settings > Developer settings), then paste it when asked"
    optional "Storing the token" security add-generic-password -U -a "$USER" -s github-pat -w
    write_profile # now with the line that reads the token
  elif [ "$os" = linux ]; then
    note "github plugin: export GITHUB_PERSONAL_ACCESS_TOKEN from a file only you can read (chmod 600), sourced by your shell profile; never in a repository"
  fi
fi

say "Done"
if [ "$status" != 0 ]; then warn "some steps reported problems (above); fix them, then run this again"; fi
note "Open a new terminal, then restart Claude Code and Codex"
note "Check the MCP servers: claude mcp list   (playwright and huggingface, connected)"
note "Your repositories: section 2 of $dir/HOW_TO_UPDATE_MACHINE_AND_ITS_REPOS.md"
exit "$status"
