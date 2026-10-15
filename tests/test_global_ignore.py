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
    conditional_ignore_files,
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


@pytest.mark.parametrize("included", ["~/.gitconfig-work", ".gitconfig-work"])
def test_an_ignore_file_named_for_some_repositories_gets_the_block_too(
    home: Path, included: str
) -> None:
    work = home / ".work-ignore"
    (home / ".gitconfig-work").write_text(f"[core]\n\texcludesFile = {work}\n")
    (home / ".gitconfig").write_text(f'[includeIf "gitdir:~/work/"]\n\tpath = {included}\n')

    planned = _sync(home, check=True)
    applied = _sync(home)
    again = _sync(home)

    always = home / ".config/git/ignore"
    assert planned.created == applied.created == [str(always), str(work)]
    assert again.unchanged == [str(always), str(work)]
    assert GITIGNORE_START in work.read_text() and GITIGNORE_START in always.read_text()


def test_a_file_this_user_cant_write_is_an_error_in_check_too(home: Path, tmp_path: Path) -> None:
    system = tmp_path / "etc-gitignore"  # the system config's, owned by root
    system.write_text("*.swp\n")
    system.chmod(0o444)
    (home / ".gitconfig").write_text(f"[core]\n\texcludesFile = {system}\n")

    planned = _sync(home, check=True)
    applied = _sync(home)

    assert planned.errors == applied.errors and len(applied.errors) == 1
    assert applied.errors[0].startswith(f"cannot write {system}") and not applied.updated
    assert system.read_text() == "*.swp\n"


def _work_ignore(home: Path, config: str = "~/.gitconfig-work") -> Path:
    """A config file, `config`, that sets core.excludesFile to ~/.work-ignore."""
    work = home / ".work-ignore"
    (home / config.removeprefix("~/")).write_text(f"[core]\n\texcludesFile = {work}\n")
    return work


@pytest.mark.parametrize(
    "layout", ["a condition with a space", "through [include]", "nested in an includeIf"]
)
def test_includeifs_are_found_however_the_config_is_laid_out(home: Path, layout: str) -> None:
    work = _work_ignore(home)
    if layout == "a condition with a space":
        gitconfig = '[includeIf "gitdir:~/My Projects/"]\n\tpath = ~/.gitconfig-work\n'
    elif layout == "through [include]":
        (home / ".dotfiles").mkdir()
        (home / ".dotfiles/gitconfig").write_text(
            '[includeIf "gitdir:~/work/"]\n\tpath = ../.gitconfig-work\n'  # relative to its file
        )
        gitconfig = "[include]\n\tpath = ~/.dotfiles/gitconfig\n"
    else:
        (home / ".gitconfig-outer").write_text(
            '[includeIf "onbranch:main"]\n\tpath = ~/.gitconfig-work\n'
        )
        gitconfig = '[includeIf "gitdir:~/work/"]\n\tpath = ~/.gitconfig-outer\n'
    (home / ".gitconfig").write_text(gitconfig)

    result = _sync(home)

    assert str(work) in result.created and GITIGNORE_START in work.read_text()


def test_a_global_config_whose_path_git_would_quote(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = home / "José/config"
    config.parent.mkdir()
    work = _work_ignore(home)
    (home / "José/work").write_text(f"[core]\n\texcludesFile = {work}\n")
    config.write_text('[includeIf "gitdir:~/work/"]\n\tpath = work\n')  # beside the config
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))

    assert conditional_ignore_files(home) == ([work], [])


def test_a_file_named_twice_or_through_a_link_is_written_once(home: Path) -> None:
    work = _work_ignore(home)
    (home / ".work-ignore-link").symlink_to(work)
    (home / ".gitconfig-link").write_text(f"[core]\n\texcludesFile = {home}/.work-ignore-link\n")
    (home / ".gitconfig").write_text(
        '[includeIf "gitdir:~/work/"]\n\tpath = ~/.gitconfig-work\n'
        '[includeIf "gitdir:~/clients/"]\n\tpath = ~/.gitconfig-work\n'
        '[includeIf "gitdir:~/more/"]\n\tpath = ~/.gitconfig-link\n'
    )

    planned = _sync(home, check=True)
    applied = _sync(home)

    always = home / ".config/git/ignore"
    assert planned.created == applied.created == [str(always), str(work)]
    assert work.read_text().count(GITIGNORE_START) == 1


def test_a_conditional_file_left_alone_doesnt_stop_the_rest(home: Path, tmp_path: Path) -> None:
    managed = tmp_path / "corp-ignore"  # a managed include's file, read-only to the user
    managed.write_text("*.swp\n")
    managed.chmod(0o444)
    (home / ".gitconfig-corp").write_text(f"[core]\n\texcludesFile = {managed}\n")
    (home / ".gitconfig-oss").write_text("[core]\n\texcludesFile = .git/info/local-ignore\n")
    (home / ".gitconfig").write_text(
        '[includeIf "gitdir:~/corp/"]\n\tpath = ~/.gitconfig-corp\n'
        '[includeIf "gitdir:~/oss/"]\n\tpath = ~/.gitconfig-oss\n'
    )

    planned = _sync(home, check=True)
    applied = _sync(home)

    assert planned.created == applied.created == [str(home / ".config/git/ignore")]
    assert not applied.errors and not applied.preserved  # globals still exits 0
    assert planned.notes == applied.notes and len(applied.notes) == 2
    assert "relative core.excludesFile (.git/info/local-ignore)" in applied.notes[0]
    assert applied.notes[1].startswith(f"{managed} (Git reads its ignores there in some")
