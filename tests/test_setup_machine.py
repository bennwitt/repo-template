"""setup-machine.sh, run in a temporary home with stand-ins for `uv`, `repo-template` and the
tools it installs: no network and no real home. A run has no terminal (a session of its own, so
it can't ask), unless it is a conversation (`_converse`), which answers in a terminal of its own."""

from __future__ import annotations

import hashlib
import io
import json
import os
import pty
import select
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NEEDS_PERMISSIONS = pytest.mark.skipif(os.geteuid() == 0, reason="root writes anything")
SCRIPT = ROOT / "setup-machine.sh"
GIT = [
    "git",
    "-c",
    "user.name=T",
    "-c",
    "user.email=t@example.com",
    "-c",
    "core.excludesFile=/dev/null",
]

UV = """#!/bin/sh
case "$1 $2" in
  "--version "*) echo "uv 0.0.0" ;;
  "tool install") echo "uv $*" >>"$HOME/calls.log"; mkdir -p "$HOME/.local/bin"
    cp "$STUBS/repo-template.stub" "$HOME/.local/bin/repo-template" ;;
  "tool dir") echo "$HOME/.local/bin" ;;
  "tool update-shell") ;;
  "run --no-project")  # uv run --no-project --no-config --no-python-downloads --quiet python ...
    [ "$PWD" = / ] || { echo "uv run from $PWD, whose .venv could decide" >&2; exit 9; }
    [ -z "${VIRTUAL_ENV-}${CONDA_PREFIX-}" ] || { echo "uv run in an activated env" >&2; exit 9; }
    case ":$PATH:" in *"/.venv/bin:"*) echo "an activated env's bin on PATH" >&2; exit 9 ;; esac
    [ "${UV_PYTHON-}" = "${KEEP_UV_PYTHON-}" ] || { echo "UV_PYTHON changed" >&2; exit 9; }
    [ -z "${UV_RUN_FAILS-}" ] || { echo "error: No interpreter found" >&2; exit 2; }
    case " $* " in *" --no-config "*) ;; *) echo "uv run reads configuration" >&2; exit 9 ;; esac
    case " $* " in *" --no-python-downloads "*) ;; *) echo "uv run downloads" >&2; exit 9 ;; esac
    case " $* " in *" python -I -S "*) ;; *) echo "python runs site or the cwd" >&2; exit 9 ;; esac
    while [ "$1" != python ]; do shift; done
    shift; exec "$PYTHON" "$@" ;;
  *) echo "uv stub: $*" >&2; exit 9 ;;
esac
"""

REPO_TEMPLATE = """#!/bin/sh
echo "repo-template $*" >>"$HOME/calls.log"
case "$*" in
  --help) exit 0 ;;
  --version) echo "repo-template 9.9.9 ($HOME/aiDevStandards)" ;;
  *--check*) printf 'Would create (2):\\n  + first-link\\n  + second-link\\n'
    exit "${CHECK_EXIT:-1}" ;;
  globals*) exit "${APPLY_EXIT:-0}" ;;
esac
"""

# The tools the script finds or installs. Each logs its call; only reads answer.
TOOLS = {
    "uname": 'case "$1" in -m) echo "${UNAME_M:-x86_64}" ;; *) echo "${UNAME_S:-Linux}" ;; esac\n',
    "node": "echo v22.11.0\n",
    "claude": "echo '2.1.0 (Claude Code)'\n",
    "az": 'echo "az $*" >>"$HOME/calls.log"\n',
    "npm": 'echo "npm $*" >>"$HOME/calls.log"\n'
    '[ "$1" != ls ] || { printf "%s" "${NPM_LS-}"; exit "${NPM_EXIT:-0}"; }\n',
    "curl": 'echo "curl $*" >>"$HOME/calls.log"\n'
    'while [ "$1" != -o ]; do shift; done\n'
    'cp "$RELEASE/${3##*/}" "$2"\n',  # curl -fsSL -o FILE URL: the release's file
}
AZD = (  # azd itself, as its release ships it; `version` also notes its update check and telemetry
    'echo "azd $*" >>"$HOME/calls.log"\n'
    '[ "$1" != version ] || echo "${AZD_SKIP_UPDATE_CHECK:-checks}'
    ' ${AZURE_DEV_COLLECT_TELEMETRY:-sends}" >>"$HOME/azd-version.log"\n'
    '[ "$1" != version ] || echo "azd version 1.2.3 (commit abc)"\n'
)
PINS = {  # package, version, published
    "codex": ("@openai/codex", "0.1.0", "2026-09-20T23:30:00Z"),
    "playwright-cli": ("@playwright/cli", "0.1.2", "2026-09-02T10:00:00Z"),
    "pyright": ("pyright", "1.1.4", "2026-09-09T20:42:01Z"),
    "typescript": ("typescript", "6.0.3", "2026-04-16T23:38:27Z"),
    "typescript-language-server": ("typescript-language-server", "5.3.0", "2026-05-21T06:35:07Z"),
}


def _git(root: Path, *args: str) -> str:
    done = subprocess.run([*GIT, "-C", str(root), *args], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.fixture
def machine(tmp_path: Path) -> dict[str, Path]:
    home, stubs, origin = tmp_path / "home", tmp_path / "stubs", tmp_path / "origin"
    home.mkdir()
    stubs.mkdir()
    (stubs / "uv").write_text(UV)
    (stubs / "repo-template.stub").write_text(REPO_TEMPLATE)
    for name, body in TOOLS.items():
        (stubs / name).write_text("#!/bin/sh\n" + body)
    for stub in stubs.iterdir():
        stub.chmod(0o755)
    release = tmp_path / "release"  # azd's release on GitHub, for linux-amd64
    release.mkdir()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        program = ("#!/bin/sh\n" + AZD).encode()
        binary = tarfile.TarInfo("azd-linux-amd64")
        binary.size, binary.mode = len(program), 0o755
        tar.addfile(binary, io.BytesIO(program))
    (release / "azd-linux-amd64.tar.gz").write_bytes(archive.getvalue())
    origin.mkdir()  # the standards repository, as GitHub has it
    (origin / "pyproject.toml").write_text('[project]\nname = "repo-template"\nversion = "9.9.9"\n')
    tools: dict[str, object] = {
        name: {"registry": "npm", "package": package, "version": version, "publishedAt": published}
        for name, (package, version, published) in PINS.items()
    }
    tools["azd"] = {
        "registry": "github",
        "package": "Azure/azure-dev",
        "tag": "azure-dev-cli_{version}",
        "version": "1.2.3",
        "assets": {
            "linux-amd64": {
                "file": "azd-linux-amd64.tar.gz",
                "sha256": hashlib.sha256(archive.getvalue()).hexdigest(),
            }
        },
    }
    (origin / ".agents").mkdir()
    (origin / ".agents/machine-tools.json").write_text(json.dumps({"schema": 1, "tools": tools}))
    _git(origin, "init", "-q", "-b", "main")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "standards")
    return {"home": home, "stubs": stubs, "origin": origin, "release": release}


def _environment(machine: dict[str, Path], **env: str) -> dict[str, str]:
    home = machine["home"]
    return {
        "HOME": str(home),
        "USER": "tester",
        "SHELL": "/bin/zsh",
        "PATH": f"{machine['stubs']}:/usr/bin:/bin",
        "STUBS": str(machine["stubs"]),
        "PYTHON": sys.executable,
        "RELEASE": str(machine["release"]),
        "REPO_TEMPLATE_URL": str(machine["origin"]),
        "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
        **env,
    }


def _run(machine: dict[str, Path], *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=machine["home"],  # a relative path in a run can only land in the temporary home
        env=_environment(machine, **env),
        capture_output=True,
        text=True,
        start_new_session=True,  # no terminal: it must never wait for an answer
        timeout=120,
    )


def _converse(
    machine: dict[str, Path], answers: list[tuple[str, str]], *args: str, **env: str
) -> tuple[int, str]:
    """A run in a terminal of its own: each answer is typed once its question appears, in
    order. Returns the exit code and everything the terminal showed; every answer must be used."""
    pid, terminal = pty.fork()
    if pid == 0:  # the child: the script, with the terminal as its own
        try:
            os.chdir(machine["home"])
            os.execve("/bin/bash", ["bash", str(SCRIPT), *args], _environment(machine, **env))
        finally:
            os._exit(127)
    shown, asked_up_to, pending, ended = "", 0, list(answers), False
    deadline = time.monotonic() + 120
    try:
        while not ended:
            ready, _, _ = select.select([terminal], [], [], max(0.0, deadline - time.monotonic()))
            if not ready:
                raise TimeoutError(shown)
            try:
                chunk = os.read(terminal, 4096)
            except OSError:  # Linux: the script exited
                chunk = b""
            ended = not chunk  # macOS reads nothing once the script exited
            shown += chunk.decode(errors="replace")
            while pending and (at := shown.find(pending[0][0], asked_up_to)) >= 0:
                asked_up_to = at + len(pending[0][0])
                os.write(terminal, (pending.pop(0)[1] + "\n").encode())
    finally:
        if not ended:
            os.kill(pid, signal.SIGKILL)
        _, status = os.waitpid(pid, 0)
        os.close(terminal)
    assert not pending, f"never asked {pending[0][0]!r}:\n{shown}"
    return os.waitstatus_to_exitcode(status), shown


def _calls(home: Path) -> list[str]:
    log = home / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def test_a_first_install_clones_installs_and_applies_then_a_second_run_changes_nothing(
    machine: dict[str, Path],
) -> None:
    home = machine["home"]
    target = home / "aiDevStandards"

    first = _run(machine, "--yes")

    assert first.returncode == 0, first.stderr
    assert (target / "pyproject.toml").is_file()
    assert _calls(home) == [
        f"uv tool install --quiet --editable --force {target}",
        "repo-template --help",
        f"repo-template globals --standards-root {target} --check",
        f"repo-template globals --standards-root {target}",
    ]
    profile = (home / ".zshrc").read_text()
    assert f'export AI_DEV_STANDARDS="{target}"' in profile

    _git(machine["origin"], "commit", "-q", "--allow-empty", "-m", "newer standards")
    (home / "calls.log").unlink()
    second = _run(machine, "--yes", CHECK_EXIT="0")

    assert second.returncode == 0, second.stderr
    assert _git(target, "rev-parse", "HEAD") == _git(machine["origin"], "rev-parse", "HEAD")
    assert "already current" in second.stdout
    assert f"repo-template globals --standards-root {target}" not in _calls(home)
    assert (home / ".zshrc").read_text() == profile and profile.count("AI_DEV_STANDARDS") == 1


def test_the_folder_is_asked_for_and_a_tilde_means_home(machine: dict[str, Path]) -> None:
    result = _run(machine, "--yes", "--dir", "~/standards", "--no-globals", "--no-tools")

    assert result.returncode == 0, result.stderr
    assert (machine["home"] / "standards/pyproject.toml").is_file()


def test_an_existing_checkout_is_the_default(machine: dict[str, Path], tmp_path: Path) -> None:
    existing = tmp_path / "elsewhere"
    _git(tmp_path, "clone", "-q", str(machine["origin"]), str(existing))
    (machine["home"] / ".agents").symlink_to(existing / ".agents")

    result = _run(machine, "--yes", "--no-globals", "--no-tools")

    assert result.returncode == 0, result.stderr
    assert f"already uses the standards repository at {existing}" in result.stdout
    assert not (machine["home"] / "aiDevStandards").exists()


def test_without_a_terminal_it_refuses_to_guess(machine: dict[str, Path]) -> None:
    result = _run(machine)

    assert result.returncode == 1 and "no terminal to ask in" in result.stderr
    assert not (machine["home"] / "aiDevStandards").exists() and not _calls(machine["home"])


@pytest.mark.parametrize("case", ["not empty", "another repository", "linked settings"])
def test_it_refuses_before_changing_anything(machine: dict[str, Path], case: str) -> None:
    home = machine["home"]
    target = home / "aiDevStandards"
    target.mkdir()
    if case == "not empty":
        (target / "notes.txt").write_text("mine\n")
        message = "isn't empty"
    elif case == "another repository":
        _git(target, "init", "-q")
        (target / "pyproject.toml").write_text('[project]\nname = "something-else"\n')
        message = "not repo-template"
    else:  # a pre-0.4.2 machine: the settings link into an older standards checkout
        old = home / "old-standards"
        _git(home, "clone", "-q", str(machine["origin"]), str(old))
        (old / ".claude").mkdir()
        (old / ".claude/settings.json").write_text("{}\n")
        (home / ".claude").mkdir()
        (home / ".claude/settings.json").symlink_to(old / ".claude/settings.json")
        message = "set up before 0.4.2"

    result = _run(machine, "--yes")

    assert result.returncode == 1 and message in result.stderr
    assert not _calls(home) and not (home / ".zshrc").exists()


def test_a_checkout_with_local_changes_isnt_pulled(machine: dict[str, Path]) -> None:
    target = machine["home"] / "aiDevStandards"
    _run(machine, "--yes", "--no-globals", "--no-tools")
    (target / "pyproject.toml").write_text('[project]\nname = "repo-template"\nversion = "local"\n')
    before = _git(target, "rev-parse", "HEAD")
    _git(machine["origin"], "commit", "-q", "--allow-empty", "-m", "newer standards")

    result = _run(machine, "--yes", "--no-globals", "--no-tools")

    assert result.returncode == 0 and "uncommitted changes, so it wasn't pulled" in result.stderr
    assert _git(target, "rev-parse", "HEAD") == before


def test_the_profile_block_replaces_an_old_one_and_keeps_the_rest(
    machine: dict[str, Path],
) -> None:
    home = machine["home"]
    (home / ".zshrc").write_text(
        "alias ll='ls -l'\n"
        "# >>> repo-template (setup-machine.sh) >>>\n"
        'export AI_DEV_STANDARDS="/old"\n'
        "# <<< repo-template (setup-machine.sh) <<<\n"
        "export EDITOR=vim\n"
    )

    result = _run(machine, "--yes", "--no-globals", "--no-tools")

    assert result.returncode == 0, result.stderr
    profile = (home / ".zshrc").read_text()
    assert "/old" not in profile and profile.count("AI_DEV_STANDARDS") == 1
    assert profile.startswith("alias ll='ls -l'\n# >>> repo-template (setup-machine.sh) >>>\n")
    assert profile.endswith("# <<< repo-template (setup-machine.sh) <<<\nexport EDITOR=vim\n")
    assert list((home / ".repo-template/backups").glob("*/.zshrc"))  # the old one, kept


def test_the_script_is_executable_and_shellcheck_finds_nothing() -> None:
    assert os.access(SCRIPT, os.X_OK)
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0
    shellcheck = shutil.which("shellcheck")  # the shellcheck-py dev dependency
    assert shellcheck, "uv sync --dev installs shellcheck"
    done = subprocess.run([shellcheck, "-s", "bash", str(SCRIPT)], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout


def test_without_a_terminal_a_named_folder_still_needs_yes(machine: dict[str, Path]) -> None:
    result = _run(machine, "--dir", "~/standards")

    assert result.returncode == 1 and "no terminal to ask in" in result.stderr
    assert not (machine["home"] / "standards").exists() and not _calls(machine["home"])


def test_a_second_run_leaves_the_profile_byte_for_byte(machine: dict[str, Path]) -> None:
    home = machine["home"]
    _run(machine, "--yes", "--no-globals", "--no-tools")
    with (home / ".zshrc").open("a") as profile:
        profile.write("export EDITOR=vim\n")  # added after the block, by hand
    before = (home / ".zshrc").read_bytes()

    result = _run(machine, "--yes", "--no-globals", "--no-tools")

    assert result.returncode == 0 and "updated" not in result.stdout
    assert "Shell profile" not in result.stdout  # a heading only when it changes something
    assert (home / ".zshrc").read_bytes() == before


def test_a_settings_link_of_your_own_isnt_taken_for_an_old_machine(
    machine: dict[str, Path], tmp_path: Path
) -> None:
    home = machine["home"]
    (tmp_path / "dotfiles/.claude").mkdir(parents=True)  # a dotfiles repository, not repo-template
    (tmp_path / "dotfiles/.claude/settings.json").write_text("{}\n")
    (home / ".claude").mkdir()
    (home / ".claude/settings.json").symlink_to(tmp_path / "dotfiles/.claude/settings.json")

    result = _run(machine, "--yes", "--no-tools")

    assert result.returncode == 0, result.stderr


def test_a_broken_block_in_the_profile_is_left_alone(machine: dict[str, Path]) -> None:
    home = machine["home"]
    broken = (
        "alias ll='ls -l'\n# >>> repo-template (setup-machine.sh) >>>\n"
        'export AI_DEV_STANDARDS="/old"\nexport EDITOR=vim\nsource ~/.secrets.sh\n'
    )
    (home / ".zshrc").write_text(broken)

    result = _run(machine, "--yes", "--no-globals", "--no-tools")

    assert result.returncode == 1 and "broken repo-template block" in result.stderr
    assert (home / ".zshrc").read_text() == broken


def test_a_failing_step_doesnt_stop_the_rest(machine: dict[str, Path]) -> None:
    result = _run(machine, "--yes", APPLY_EXIT="1")

    assert result.returncode == 1 and "reported errors" in result.stderr
    assert "AI_DEV_STANDARDS" in (machine["home"] / ".zshrc").read_text()
    assert "==> Optional tools" in result.stdout and "==> Done" in result.stdout  # the steps after


def test_git_must_really_run(machine: dict[str, Path], tmp_path: Path) -> None:
    shim = tmp_path / "shim"  # a new Mac's /usr/bin/git, before the command line tools
    shim.mkdir()
    (shim / "git").write_text(
        "#!/bin/sh\necho 'xcrun: error: invalid active developer path' >&2\nexit 1\n"
    )
    (shim / "git").chmod(0o755)

    result = _run(machine, "--yes", PATH=f"{shim}:{machine['stubs']}:/usr/bin:/bin")

    assert result.returncode == 1 and "git is needed" in result.stderr
    assert not (machine["home"] / "aiDevStandards").exists()


def test_a_dragged_or_pasted_folder_is_cleaned_up(machine: dict[str, Path]) -> None:
    result = _run(machine, "--yes", "--dir", " ~/My\\ Standards ", "--no-globals", "--no-tools")

    assert result.returncode == 0, result.stderr
    assert (machine["home"] / "My Standards/pyproject.toml").is_file()
    assert [p.name for p in machine["home"].iterdir() if "Standards" in p.name] == ["My Standards"]


def test_zsh_with_zdotdir_gets_its_own_zshrc(machine: dict[str, Path]) -> None:
    zdotdir = machine["home"] / ".config/zsh"

    result = _run(machine, "--yes", "--no-globals", "--no-tools", ZDOTDIR=str(zdotdir))

    assert result.returncode == 0, result.stderr
    assert "AI_DEV_STANDARDS" in (zdotdir / ".zshrc").read_text()
    assert not (machine["home"] / ".zshrc").exists()


def test_bash_on_a_mac_writes_to_the_startup_file_it_already_reads(
    machine: dict[str, Path],
) -> None:
    home = machine["home"]
    (home / ".profile").write_text("export FROM_PROFILE=yes\n")

    result = _run(
        machine, "--yes", "--no-globals", "--no-tools", SHELL="/bin/bash", UNAME_S="Darwin"
    )

    assert result.returncode == 0, result.stderr
    assert not (home / ".bash_profile").exists()  # it would hide ~/.profile from login shells
    assert (
        (home / ".profile").read_text().startswith("export FROM_PROFILE=yes\n\n# >>> repo-template")
    )


def test_a_first_run_summarizes_the_globals_plan_and_a_later_one_lists_it(
    machine: dict[str, Path],
) -> None:
    home = machine["home"]

    first = _run(machine, "--yes", "--no-tools")
    (home / ".repo-template").mkdir(exist_ok=True)
    (home / ".repo-template/globals-state.json").write_text("{}")  # set up before
    later = _run(machine, "--yes", "--no-tools")

    assert "a first run: 2 to create, 0 to update, 0 to remove, 0 to review" in first.stdout
    assert "+ first-link" not in first.stdout
    assert "+ first-link" in later.stdout and "a first run" not in later.stdout


def test_a_pull_that_brings_a_new_version_says_so(machine: dict[str, Path]) -> None:
    origin = machine["origin"]
    _run(machine, "--yes", "--no-globals", "--no-tools")
    (origin / "pyproject.toml").write_text(
        '[project]\nname = "repo-template"\nversion = "9.9.10"\n'
    )
    _git(origin, "commit", "-q", "-am", "release")

    result = _run(machine, "--yes", "--no-globals", "--no-tools")

    assert "repo-template 9.9.9 -> 9.9.10" in result.stdout


def test_a_settings_link_whose_file_a_pull_removed_is_reported_and_passed(
    machine: dict[str, Path],
) -> None:
    home = machine["home"]
    old = home / "old-standards"
    _git(home, "clone", "-q", str(machine["origin"]), str(old))
    (home / ".claude").mkdir()
    (home / ".claude/settings.json").symlink_to(old / ".claude/settings.json")  # dangles

    result = _run(machine, "--yes", "--no-tools")

    assert result.returncode == 0, result.stderr
    assert "globals writes fresh settings in its place" in result.stderr


def _set_up(machine: dict[str, Path]) -> Path:
    """A machine this script has set up: the checkout, the CLI, and the ~/.agents link."""
    target = machine["home"] / "aiDevStandards"
    assert _run(machine, "--yes", "--no-globals", "--no-tools").returncode == 0
    (machine["home"] / ".agents").symlink_to(target / ".agents")
    (machine["home"] / "calls.log").unlink()
    return target


def _npm_has(**versions: str) -> str:
    return json.dumps(
        {"dependencies": {PINS[name][0]: {"version": v} for name, v in versions.items()}}
    )


def _tool_calls(home: Path) -> list[str]:
    return [call for call in _calls(home) if not call.startswith(("uv ", "repo-template "))]


def _snapshot(home: Path) -> list[tuple[str, int, int]]:
    """Every file under home, with its size and modification time."""
    return sorted(
        (str(p), p.lstat().st_size, p.lstat().st_mtime_ns) for p in home.rglob("*") if p.is_file()
    )


def _installed(stubs: Path, name: str, body: str) -> None:
    (stubs / name).write_text("#!/bin/sh\n" + body)
    (stubs / name).chmod(0o755)


def test_check_reports_a_machine_that_is_set_up_and_changes_nothing(
    machine: dict[str, Path],
) -> None:
    home, stubs = machine["home"], machine["stubs"]
    target = _set_up(machine)
    _installed(stubs, "azd", AZD)
    before = _snapshot(home)
    everything = {name: version for name, (_, version, _) in PINS.items()}

    result = _run(
        machine, "--check",
        PATH=f"{stubs}:{home}/.local/bin:/usr/bin:/bin", AI_DEV_STANDARDS=str(target),
        CHECK_EXIT="0", NPM_LS=_npm_has(**everything),
    )  # fmt: skip

    assert result.returncode == 0, result.stdout + result.stderr
    assert "!" not in result.stdout and "==> All set" in result.stdout
    for line in ("its main is up to date with GitHub's", "repo-template on PATH runs from it",
                 "globals: current", "typescript 6.0.3", "azd 1.2.3"):  # fmt: skip
        assert f"ok  {line}" in result.stdout
    assert _calls(home) == [  # only reads
        "repo-template --version",
        f"repo-template globals --check --standards-root {target}",
        "npm ls -g --depth=0 --json",
        "azd version",
    ]
    assert (home / "azd-version.log").read_text() == "1 no\n"  # no update check, no telemetry
    (home / "calls.log").unlink()
    (home / "azd-version.log").unlink()
    assert _snapshot(home) == before  # nothing else written, not even Git's index


def test_check_lists_each_problem_and_fails(machine: dict[str, Path]) -> None:
    home, stubs = machine["home"], machine["stubs"]
    target = _set_up(machine)
    _git(machine["origin"], "commit", "-q", "--allow-empty", "-m", "newer standards")
    _installed(stubs, "azd", AZD.replace("1.2.3", "1.0.0"))
    _installed(stubs, "node", "echo v20.9.0\n")

    result = _run(
        machine, "--check",
        PATH=f"{stubs}:{home}/.local/bin:/usr/bin:/bin", NPM_LS=_npm_has(typescript="5.9.0"),
    )  # fmt: skip

    assert result.returncode == 1
    problems = [line.strip() for line in result.stdout.splitlines() if line.startswith("    !")]
    assert problems == [
        "!   node v20.9.0: past its end of life; install 22 or 24 LTS",
        "!   GitHub's main has moved on: run this script, or git pull",
        f"!   AI_DEV_STANDARDS isn't {target} in this shell: open a new terminal",
        "!   globals has changes to make: 'repo-template globals --check' lists them",
        "!   typescript 5.9.0: the pin is 6.0.3 (run this script and answer yes to install it)",
        f"!   {stubs}/azd is 'azd version 1.0.0 (commit abc)', not the pinned azd 1.2.3: remove "
        "it (Homebrew: brew uninstall azd), then run this script and answer yes to Azure",
    ]
    assert "==> 6 to fix" in result.stdout
    assert "pyright: not installed (optional; this script offers 1.1.4)" in result.stdout


def test_check_without_a_standards_link_says_how_to_set_up(machine: dict[str, Path]) -> None:
    result = _run(machine, "--check", "--offline")

    assert result.returncode == 1
    assert f"{machine['home']}/.agents isn't a link into a standards repository" in result.stdout
    assert not (machine["home"] / "aiDevStandards").exists()


def test_the_tools_install_at_their_pins_and_azd_only_with_its_checksum(
    machine: dict[str, Path],
) -> None:
    home = machine["home"]
    target = _set_up(machine)

    code, shown = _converse(
        machine,
        [("language servers", "y"), ("Codex CLI", "y"), ("Azure CLI and azd", "y")],
        "--dir", str(target), "--no-globals",
    )  # fmt: skip

    assert code == 0, shown
    npm, codex, download, *rest = _tool_calls(home)
    assert npm == (  # dependencies too: none newer than the end of the newest pin's day
        "npm install -g --ignore-scripts --before=2026-09-10T00:00:00Z "
        "typescript-language-server@5.3.0 typescript@6.0.3 pyright@1.1.4 @playwright/cli@0.1.2"
    )
    assert codex == (
        "npm install -g --ignore-scripts --before=2026-09-21T00:00:00Z @openai/codex@0.1.0"
    )
    assert download.startswith("curl -fsSL -o ") and download.endswith(
        " https://github.com/Azure/azure-dev/releases/download/azure-dev-cli_1.2.3/"
        "azd-linux-amd64.tar.gz"
    )
    assert rest == ["az account show", "azd config set auth.useAzCliAuth true"]
    assert os.access(home / ".local/bin/azd", os.X_OK) and "SHA-256 checked" in shown


def test_an_azd_download_that_doesnt_match_its_pin_isnt_installed(
    machine: dict[str, Path],
) -> None:
    home = machine["home"]
    target = _set_up(machine)
    (machine["release"] / "azd-linux-amd64.tar.gz").write_bytes(b"something else")

    code, shown = _converse(
        machine,
        [("language servers", "n"), ("Codex CLI", "n"), ("Azure CLI and azd", "y")],
        "--dir", str(target), "--no-globals",
    )  # fmt: skip

    assert code == 0, shown  # an optional tool: reported, never fatal
    assert "not the pinned" in shown and "run this script again and answer yes to Azure" in shown
    assert "install_azd" not in shown  # a function of the script's, not a command to run
    assert not (home / ".local/bin/azd").exists()
    assert [call.split(" ")[0] for call in _tool_calls(home)] == ["curl", "az"]


def _check(machine: dict[str, Path], *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    home, stubs = machine["home"], machine["stubs"]
    return _run(machine, "--check", *args, PATH=f"{stubs}:{home}/.local/bin:/usr/bin:/bin", **env)


def _problems(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [line.strip() for line in result.stdout.splitlines() if line.startswith("    !")]


def test_check_reports_an_origin_it_cant_reach_and_goes_on(
    machine: dict[str, Path], tmp_path: Path
) -> None:
    _set_up(machine)
    machine["origin"].rename(tmp_path / "gone")  # offline, or GitHub down

    result = _check(machine)

    assert result.returncode == 1
    assert "!   its origin couldn't be reached (--offline skips this)" in _problems(result)
    assert "to fix (the ! lines)" in result.stdout  # every check after it ran


def test_check_tells_a_checkout_ahead_of_github_to_push(machine: dict[str, Path]) -> None:
    target = _set_up(machine)
    _git(target, "commit", "-q", "--allow-empty", "-m", "mine, not pushed")

    result = _check(machine)

    assert "!   its main has commits GitHub's doesn't: push them, or move them to a branch" in (
        _problems(result)
    )
    assert "moved on" not in result.stdout


def test_check_goes_on_when_a_tool_fails_to_run(machine: dict[str, Path]) -> None:
    _set_up(machine)
    _installed(machine["stubs"], "node", "exit 1\n")  # a version manager's shim, say
    _installed(machine["stubs"], "azd", "exit 1\n")

    result = _check(machine, "--offline")

    assert result.returncode == 1
    assert "!   node on PATH: its version can't be read" in _problems(result)
    assert any(line.startswith(f"!   {machine['stubs']}/azd is ''") for line in _problems(result))
    assert "to fix (the ! lines)" in result.stdout


def test_a_folder_reached_through_a_link_is_recorded_as_its_real_path(
    machine: dict[str, Path], tmp_path: Path
) -> None:
    home = machine["home"]
    (tmp_path / "data/code").mkdir(parents=True)
    (home / "code").symlink_to(tmp_path / "data/code")
    real = tmp_path / "data/code/std"

    result = _run(machine, "--yes", "--dir", "~/code/std", "--no-globals", "--no-tools")

    assert result.returncode == 0, result.stderr
    assert f'export AI_DEV_STANDARDS="{real}"' in (home / ".zshrc").read_text()
    (home / ".agents").symlink_to(real / ".agents")  # as globals links it
    checked = _check(machine, "--offline", AI_DEV_STANDARDS=str(home / "code/std"))
    assert "ok  AI_DEV_STANDARDS is set" in checked.stdout


def test_an_azd_that_isnt_the_pin_is_replaced(machine: dict[str, Path]) -> None:
    home = machine["home"]
    target = _set_up(machine)
    (home / ".local/bin/azd").write_text("#!/bin/sh\n" + AZD.replace("1.2.3", "1.0.0"))
    (home / ".local/bin/azd").chmod(0o755)

    code, shown = _converse(
        machine,
        [("language servers", "n"), ("Codex CLI", "n"), ("Azure CLI and azd", "y")],
        "--dir", str(target), "--no-globals",
        PATH=f"{machine['stubs']}:{home}/.local/bin:/usr/bin:/bin",
    )  # fmt: skip

    assert code == 0, shown
    asked, download, *rest = _tool_calls(home)
    assert asked == "azd version" and download.startswith("curl ")
    assert rest == ["az account show", "azd config set auth.useAzCliAuth true"]
    assert "1.2.3" in (home / ".local/bin/azd").read_text()
    assert "brew uninstall" not in shown  # it was ours, in ~/.local/bin


def test_another_azd_first_on_path_is_named_and_the_pin_installed(
    machine: dict[str, Path],
) -> None:
    home = machine["home"]
    target = _set_up(machine)
    _installed(machine["stubs"], "azd", AZD.replace("1.2.3", "1.0.0"))  # Homebrew's, say

    code, shown = _converse(
        machine,
        [("language servers", "n"), ("Codex CLI", "n"), ("Azure CLI and azd", "y")],
        "--dir", str(target), "--no-globals",
    )  # fmt: skip

    assert code == 0, shown
    assert f"{machine['stubs']}/azd is another azd ('azd version 1.0.0 (commit abc)')" in shown
    assert "brew uninstall azd" in shown and "1.2.3" in (home / ".local/bin/azd").read_text()


@NEEDS_PERMISSIONS
def test_an_azd_that_cant_be_written_isnt_reported_as_installed(
    machine: dict[str, Path],
) -> None:
    home = machine["home"]
    target = _set_up(machine)
    (home / ".local/bin").chmod(0o555)  # owned by root after a sudo install, say
    try:
        code, shown = _converse(
            machine,
            [("language servers", "n"), ("Codex CLI", "n"), ("Azure CLI and azd", "y")],
            "--dir", str(target), "--no-globals",
        )  # fmt: skip
    finally:
        (home / ".local/bin").chmod(0o755)

    assert code == 0, shown
    assert "installed azd" not in shown and "azd wasn't installed" in shown
    assert not (home / ".local/bin/azd").exists()


def test_python_never_imports_from_the_folder_it_runs_in(machine: dict[str, Path]) -> None:
    home = machine["home"]
    target = _set_up(machine)
    (home / "json.py").write_text(f"open({str(home / 'planted')!r}, 'w').close()\n")

    _check(machine, "--offline", NPM_LS="{}")
    _converse(
        machine,
        [("language servers", "y"), ("Codex CLI", "n"), ("Azure CLI and azd", "y")],
        "--dir", str(target), "--no-globals",
    )  # fmt: skip

    assert not (home / "planted").exists()
    assert any("--before=" in call for call in _tool_calls(home))  # the pins were read


def test_another_azd_is_left_alone_when_nothing_replaces_it(machine: dict[str, Path]) -> None:
    target = _set_up(machine)
    _installed(machine["stubs"], "azd", AZD.replace("1.2.3", "1.0.0"))  # Homebrew's, say
    (machine["release"] / "azd-linux-amd64.tar.gz").write_bytes(b"not the release")

    code, shown = _converse(
        machine,
        [("language servers", "n"), ("Codex CLI", "n"), ("Azure CLI and azd", "y")],
        "--dir", str(target), "--no-globals",
    )  # fmt: skip

    assert code == 0, shown
    assert "azd wasn't installed" in shown and "brew uninstall" not in shown


def test_a_checkout_that_pins_no_azd_leaves_azd_as_it_is(machine: dict[str, Path]) -> None:
    home = machine["home"]
    target = _set_up(machine)
    pins = json.loads((target / ".agents/machine-tools.json").read_text())
    del pins["tools"]["azd"]  # an older checkout, not pulled
    (target / ".agents/machine-tools.json").write_text(json.dumps(pins))
    _installed(machine["stubs"], "azd", AZD.replace("1.2.3", "1.0.0"))

    code, shown = _converse(
        machine,
        [("language servers", "n"), ("Codex CLI", "n"), ("Azure CLI and azd", "y")],
        "--dir", str(target), "--no-globals",
    )  # fmt: skip

    assert code == 0, shown
    assert "pins no azd" in shown and "brew uninstall" not in shown
    assert not any(call.startswith("curl") for call in _tool_calls(home))


def test_a_folder_with_dot_dot_after_a_link_is_the_one_the_system_opens(
    machine: dict[str, Path], tmp_path: Path
) -> None:
    home = machine["home"]
    (tmp_path / "data/code").mkdir(parents=True)
    (home / "code").symlink_to(tmp_path / "data/code")
    _git(tmp_path, "clone", "-q", str(machine["origin"]), str(tmp_path / "data/std"))
    (home / "std").mkdir()  # what the text ~/code/../std would name instead

    result = _run(machine, "--yes", "--dir", "~/code/../std", "--no-globals", "--no-tools")

    assert result.returncode == 0, result.stderr
    assert f"Standards repository: {tmp_path / 'data/std'}" in result.stdout
    assert not any((home / "std").iterdir())


def test_check_on_a_branch_doesnt_call_main_ahead(machine: dict[str, Path]) -> None:
    target = _set_up(machine)
    _git(target, "switch", "-q", "-c", "fix")
    _git(target, "commit", "-q", "--allow-empty", "-m", "on a branch")

    result = _check(machine)

    assert "!   it is on branch fix, not main" in _problems(result)
    assert "ok  its main is up to date with GitHub's" in result.stdout
    assert not any("commits GitHub's doesn't" in line for line in _problems(result))


@pytest.mark.parametrize(
    ("listing", "code"),
    [("npm ERR! something broke", "1"), ('{"error": {"code": "ENOTDIR"}}', "236")],
)
def test_check_flags_a_claude_or_npm_that_doesnt_run(
    machine: dict[str, Path], listing: str, code: str
) -> None:
    _set_up(machine)
    _installed(machine["stubs"], "claude", "exit 1\n")

    result = _check(machine, "--offline", NPM_LS=listing, NPM_EXIT=code)

    assert "!   claude is on PATH, but 'claude --version' fails" in _problems(result)
    assert "!   'npm ls -g' fails, so the npm tools can't be checked" in _problems(result)
    assert "this script offers" not in result.stdout  # npm said nothing about the tools


def test_check_with_an_environment_activated_still_reads_the_pins(
    machine: dict[str, Path], tmp_path: Path
) -> None:
    _set_up(machine)
    project = tmp_path / "project/.venv"  # a project's, activated in this shell

    result = _run(
        machine, "--check", "--offline", NPM_LS="{}",
        VIRTUAL_ENV=str(project), CONDA_PREFIX=str(project),
        PATH=f"{project}/bin:{machine['stubs']}:{machine['home']}/.local/bin:/usr/bin:/bin",
        UV_PYTHON="/opt/python3", KEEP_UV_PYTHON="/opt/python3",  # the owner's choice: kept
    )  # fmt: skip

    assert "pyright: not installed (optional; this script offers 1.1.4)" in result.stdout


def test_check_takes_an_empty_global_npm_folder_as_nothing_installed(
    machine: dict[str, Path],
) -> None:
    _set_up(machine)  # npm's own prefix, with no lib/ yet: `npm ls -g` reports ENOENT

    result = _check(machine, "--offline", NPM_LS='{"error": {"code": "ENOENT"}}', NPM_EXIT="254")

    assert not any("npm" in line for line in _problems(result))
    assert "pyright: not installed (optional; this script offers 1.1.4)" in result.stdout


def test_a_uv_that_cant_run_python_is_reported_not_taken_for_no_pins(
    machine: dict[str, Path],
) -> None:
    target = _set_up(machine)
    _installed(machine["stubs"], "azd", AZD.replace("1.2.3", "1.0.0"))

    checked = _check(machine, "--offline", NPM_LS="{}", UV_RUN_FAILS="1")
    code, shown = _converse(
        machine,
        [("language servers", "y"), ("Codex CLI", "n"), ("Azure CLI and azd", "y")],
        "--dir", str(target), "--no-globals", UV_RUN_FAILS="1",
    )  # fmt: skip

    assert checked.returncode == 1 and any("uv can't run Python" in p for p in _problems(checked))
    assert "All set" not in checked.stdout
    assert "uv can't run Python" in shown and "pins no azd" not in shown
    assert not any(
        call.startswith(("npm install", "curl")) for call in _tool_calls(machine["home"])
    )
