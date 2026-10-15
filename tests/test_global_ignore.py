"""globals writes its ignore block to the file Git reads: core.excludesFile (through includes, with
~ expanded), else $XDG_CONFIG_HOME/git/ignore on this machine, else ~/.config/git/ignore."""

from __future__ import annotations

import getpass
import pwd
import subprocess
from pathlib import Path

import pytest

from repo_template.model import Result
from repo_template.standards import (
    GITIGNORE_END,
    GITIGNORE_START,
    _sync_global_gitignore,
    global_ignore_file,
)


def _sync(home: Path, *, check: bool = False) -> Result:
    result = Result(home)
    _sync_global_gitignore(home, result, check=check, stamp="20261014-000000")
    return result


@pytest.fixture
def home(tmp_path: Path) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    return path


def test_without_configuration_it_is_the_xdg_default(home: Path) -> None:
    result = _sync(home)

    target = home / ".config/git/ignore"
    assert result.created == [str(target)] and GITIGNORE_START in target.read_text()


@pytest.mark.parametrize("spelling", ["absolute", "tilde", "included"])
def test_the_file_core_excludesfile_names(home: Path, spelling: str) -> None:
    mine = home / ".gitignore_global"
    mine.write_text(".DS_Store\n")
    value = str(mine) if spelling == "absolute" else "~/.gitignore_global"
    if spelling == "included":
        (home / ".gitconfig-extra").write_text(f"[core]\n\texcludesFile = {value}\n")
        (home / ".gitconfig").write_text("[include]\n\tpath = ~/.gitconfig-extra\n")
    else:
        (home / ".gitconfig").write_text(f"[core]\n\texcludesFile = {value}\n")

    result = _sync(home)

    assert global_ignore_file(home) == mine and result.updated == [str(mine)]
    assert mine.read_text().startswith(".DS_Store\n\n" + GITIGNORE_START)
    assert not (home / ".config/git/ignore").exists()
    assert (home / ".repo-template/backups/20261014-000000/git-ignore").read_text() == ".DS_Store\n"


def test_xdg_config_home_counts_on_this_machine(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "xdg"))

    assert global_ignore_file(home) == home / "xdg/git/ignore"


def test_another_homes_xdg_setting_is_ignored(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "xdg"))  # this process's, not that home's

    assert global_ignore_file(home) == home / ".config/git/ignore"


def test_a_linked_file_is_written_through(home: Path, tmp_path: Path) -> None:
    dotfiles = tmp_path / "dotfiles/ignore"
    dotfiles.parent.mkdir()
    dotfiles.write_text("*.swp\n")
    (home / ".config/git").mkdir(parents=True)
    (home / ".config/git/ignore").symlink_to(dotfiles)

    _sync(home)

    assert (home / ".config/git/ignore").is_symlink()
    assert dotfiles.read_text().startswith("*.swp\n\n" + GITIGNORE_START)


def test_a_broken_block_is_kept_and_reported(home: Path) -> None:
    target = home / ".config/git/ignore"
    target.parent.mkdir(parents=True)
    broken = f"*.swp\n{GITIGNORE_START}\n**/.claude/\nmine/\n"
    target.write_text(broken)

    result = _sync(home)

    assert target.read_text() == broken
    assert result.preserved == [f"{target} (repo-template's block has lost a marker line; kept)"]


def test_check_writes_nothing_and_a_second_run_is_current(home: Path) -> None:
    planned = _sync(home, check=True)
    assert not (home / ".config").exists()

    applied = _sync(home)
    again = _sync(home)

    assert planned.created == applied.created and again.unchanged == applied.created
    assert GITIGNORE_END in (home / ".config/git/ignore").read_text()


def test_a_conditional_include_for_some_repository_never_decides_it(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (home / ".gitconfig-work").write_text("[core]\n\texcludesFile = ~/.work-ignore\n")
    (home / ".gitconfig").write_text('[includeIf "gitdir:~/work/"]\n\tpath = ~/.gitconfig-work\n')
    project = home / "work/project"
    project.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(project)  # where `globals` happens to run

    assert global_ignore_file(home) == home / ".config/git/ignore"


def test_git_expands_the_path_itself(home: Path) -> None:
    user = getpass.getuser()
    (home / ".gitconfig").write_text(f"[core]\n\texcludesFile = ~{user}/.gitignore_x\n")

    assert global_ignore_file(home) == Path(pwd.getpwnam(user).pw_dir) / ".gitignore_x"


def test_a_relative_excludesfile_is_reported_not_guessed(home: Path) -> None:
    (home / ".gitconfig").write_text("[core]\n\texcludesFile = .gitignore_x\n")

    result = _sync(home)

    assert len(result.preserved) == 1 and "a relative path" in result.preserved[0]
    assert sorted(p.name for p in home.iterdir()) == [".gitconfig"]  # nothing written


def test_another_homes_system_config_is_ignored(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system = tmp_path / "gitconfig"
    system.write_text(f"[core]\n\texcludesFile = {tmp_path / 'system-ignore'}\n")
    monkeypatch.delenv("GIT_CONFIG_NOSYSTEM")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(system))

    assert global_ignore_file(home) == home / ".config/git/ignore"
    monkeypatch.setattr(Path, "home", lambda: home)  # now it is this machine's home
    assert global_ignore_file(home) == tmp_path / "system-ignore"


def test_markers_in_the_wrong_order_are_a_broken_block(home: Path) -> None:
    target = home / ".config/git/ignore"
    target.parent.mkdir(parents=True)
    broken = f"{GITIGNORE_END}\n*.swp\n{GITIGNORE_START}\n"
    target.write_text(broken)

    planned = _sync(home, check=True)
    applied = _sync(home)

    assert target.read_text() == broken and planned.preserved == applied.preserved
    assert applied.preserved == [f"{target} (repo-template's block has lost a marker line; kept)"]
