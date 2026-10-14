"""setup-machine.sh, run in a temporary home with stand-ins for `uv` and `repo-template`: no
network, no real home, no terminal (each run gets a session of its own, so it can't ask)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "setup-machine.sh"
GIT = ["git", "-c", "user.name=T", "-c", "user.email=t@example.com"]
IGNORE = (
    "# >>> repo-template personal AI directories\n**/.claude/\n"
    "# <<< repo-template personal AI directories\n"
)

UV = """#!/bin/sh
case "$1 $2" in
  "--version "*) echo "uv 0.0.0" ;;
  "tool install") echo "uv $*" >>"$HOME/calls.log"; mkdir -p "$HOME/.local/bin"
    cp "$STUBS/repo-template.stub" "$HOME/.local/bin/repo-template" ;;
  "tool dir") echo "$HOME/.local/bin" ;;
  "tool update-shell") ;;
  *) echo "uv stub: $*" >&2; exit 9 ;;
esac
"""

REPO_TEMPLATE = """#!/bin/sh
echo "repo-template $*" >>"$HOME/calls.log"
case "$*" in
  --help) exit 0 ;;
  *--check*) printf 'Would create (2):\\n  + first-link\\n  + second-link\\n'
    exit "${CHECK_EXIT:-1}" ;;
  globals*) mkdir -p "$HOME/.config/git"; printf '%s' "$IGNORE" >"$HOME/.config/git/ignore"
    exit "${APPLY_EXIT:-0}" ;;
esac
"""


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
    for stub in (stubs / "uv", stubs / "repo-template.stub"):
        stub.chmod(0o755)
    origin.mkdir()  # the standards repository, as GitHub has it
    (origin / "pyproject.toml").write_text('[project]\nname = "repo-template"\nversion = "9.9.9"\n')
    _git(origin, "init", "-q", "-b", "main")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "standards")
    return {"home": home, "stubs": stubs, "origin": origin}


def _run(machine: dict[str, Path], *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    home = machine["home"]
    environment = {
        "HOME": str(home),
        "USER": "tester",
        "SHELL": "/bin/zsh",
        "PATH": f"{machine['stubs']}:/usr/bin:/bin",
        "STUBS": str(machine["stubs"]),
        "IGNORE": IGNORE,
        "REPO_TEMPLATE_URL": str(machine["origin"]),
        "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
        **env,
    }
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=home,  # a relative path in a run can only land in the temporary home
        env=environment,
        capture_output=True,
        text=True,
        start_new_session=True,  # no terminal: it must never wait for an answer
        timeout=120,
    )


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


def test_ignores_are_copied_where_git_reads_them(machine: dict[str, Path]) -> None:
    home = machine["home"]
    mine = home / ".gitignore_global"
    mine.write_text(".DS_Store\n")
    (home / ".gitconfig").write_text(f"[core]\n\texcludesFile = {mine}\n")

    first = _run(machine, "--yes", "--no-tools")
    second = _run(machine, "--yes", "--no-tools")

    assert first.returncode == second.returncode == 0, first.stderr + second.stderr
    assert mine.read_text() == ".DS_Store\n\n" + IGNORE  # once, after the user's own lines


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
    home = machine["home"]
    mine = home / ".gitignore_global"
    (home / ".gitconfig").write_text(f"[core]\n\texcludesFile = {mine}\n")

    result = _run(machine, "--yes", "--no-tools", APPLY_EXIT="1")

    assert result.returncode == 1 and "reported errors" in result.stderr
    assert "AI_DEV_STANDARDS" in (home / ".zshrc").read_text()
    assert mine.read_text() == IGNORE and "==> Done" in result.stdout  # the steps after it ran


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
    machine: dict[str, Path], tmp_path: Path
) -> None:
    mac = tmp_path / "mac"
    mac.mkdir()
    (mac / "uname").write_text("#!/bin/sh\necho Darwin\n")
    (mac / "uname").chmod(0o755)
    home = machine["home"]
    (home / ".profile").write_text("export FROM_PROFILE=yes\n")

    result = _run(
        machine, "--yes", "--no-globals", "--no-tools",
        SHELL="/bin/bash", PATH=f"{mac}:{machine['stubs']}:/usr/bin:/bin",
    )  # fmt: skip

    assert result.returncode == 0, result.stderr
    assert not (home / ".bash_profile").exists()  # it would hide ~/.profile from login shells
    assert (
        (home / ".profile").read_text().startswith("export FROM_PROFILE=yes\n\n# >>> repo-template")
    )


def test_the_ignore_copy_is_kept_current_even_without_globals(machine: dict[str, Path]) -> None:
    home = machine["home"]
    (home / ".config/git").mkdir(parents=True)
    (home / ".config/git/ignore").write_text(IGNORE)  # written by an earlier globals
    mine = home / ".gitignore_global"
    stale = IGNORE.replace("**/.claude/\n", "**/.old/\n")
    mine.write_text(".DS_Store\n\n" + stale)
    (home / ".gitconfig").write_text(f"[core]\n\texcludesFile = {mine}\n")

    result = _run(machine, "--yes", "--no-globals", "--no-tools")

    assert result.returncode == 0, result.stderr
    assert mine.read_text() == ".DS_Store\n\n" + IGNORE


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
