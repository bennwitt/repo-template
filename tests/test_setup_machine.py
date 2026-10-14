"""setup-machine.sh, run in a temporary home with stand-ins for `uv` and `repo-template`: no
network, no real home, no terminal (each run gets a session of its own, so it can't ask)."""

from __future__ import annotations

import os
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
  *--check*) exit "${CHECK_EXIT:-1}" ;;
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
    else:
        (home / ".claude").mkdir()
        (home / ".claude/settings.json").symlink_to(target / "settings.json")
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
    assert profile.startswith("alias ll='ls -l'\nexport EDITOR=vim\n")


def test_the_script_is_executable_and_shellcheck_style_safe() -> None:
    assert os.access(SCRIPT, os.X_OK)
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0


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

    assert result.returncode == 0 and "Shell profile" not in result.stdout
    assert (home / ".zshrc").read_bytes() == before
