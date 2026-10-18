"""The pre-push hook that fills in a pull request's description: stand-ins for `gh` and
`claude` keep a pull request's state in files, so each test sets it up and reads back what the
hook did."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from repo_template.scaffold import new_project

MARKER = "<!-- Written by .githooks/pre-push; rewritten on each push until edited. hash:"

GH = r"""#!/bin/sh
state=__STATE__
echo "$*" >>"$state/calls"
case "$1 $2" in
  "pr view")
    case "$*" in
      *headRefOid*)
        if [ -f "$state/error" ]; then cat "$state/error" >&2; exit 1; fi
        pr="$(cat "$state/state") $(cat "$state/head")"
        case "$*" in
          *number,state,headRefOid*) echo "$(cat "$state/number") $pr" ;;
          *) echo "$pr" ;;
        esac ;;
      *"--json body"*) cat "$state/body"; echo ;;
      *"--json commits"*) cat "$state/messages" ;;
    esac ;;
  "pr edit") cp "$5" "$state/edited" && cp "$5" "$state/body" ;;
esac
"""

CLAUDE = r"""#!/bin/sh
state=__STATE__
printf '%s\n' "$@" >"$state/claude-args"
cat >"$state/prompt"
if [ -f "$state/during" ]; then sh "$state/during"; fi
if [ -f "$state/claude-fails" ]; then echo "boom" >&2; exit 1; fi
cat "$state/reply"
"""

REPLY = "## Description\n\nAdds the feature.\n"


@dataclass
class Repo:
    root: Path
    state: Path
    env: dict[str, str]
    oid: str

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.root), *args], capture_output=True, text=True, env=self.env
        )

    def fill(self) -> subprocess.CompletedProcess[str]:
        """The background half, run in the foreground: what a push of `feature` starts."""
        return subprocess.run(
            ["sh", ".githooks/pre-push", "--fill", "feature", self.oid],
            cwd=self.root, capture_output=True, text=True, env=self.env, timeout=60,
        )  # fmt: skip

    def set(self, **files: str) -> None:
        for name, text in files.items():
            (self.state / name).write_text(text)

    def calls(self) -> list[str]:
        calls = self.state / "calls"
        return calls.read_text().splitlines() if calls.is_file() else []

    def edited(self) -> str | None:
        edited = self.state / "edited"
        return edited.read_text() if edited.is_file() else None


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    """A generated repository on `feature`, one commit ahead of main, pushed to a bare remote;
    its open pull request #7 shows that commit and has an empty description."""
    root = tmp_path / "repo"
    new_project(root, name="repo", description="R.", python_version="3.12")
    state = tmp_path / "state"
    stubs = tmp_path / "bin"
    state.mkdir()
    stubs.mkdir()
    for name, script in (("gh", GH), ("claude", CLAUDE)):
        (stubs / name).write_text(script.replace("__STATE__", str(state)))
        (stubs / name).chmod(0o755)
    git_dir = Path(shutil.which("git") or "/usr/bin/git").parent
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{stubs}:{git_dir}:/usr/bin:/bin",  # no real claude or gh
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
        "PR_DESCRIPTION_WAIT": "0",
    }  # fmt: skip
    (tmp_path / "home").mkdir()
    made = Repo(root, state, env, "")
    remote = tmp_path / "remote.git"
    for args in (
        ("init", "-q", "-b", "main"),
        ("add", "-A"),
        ("commit", "-qm", "Start"),
        ("init", "-q", "--bare", str(remote)),
        ("remote", "add", "origin", str(remote)),
        ("push", "-q", "origin", "main"),
        ("switch", "-q", "-c", "feature"),
        ("commit", "-q", "--allow-empty", "-m", "First change"),
        ("commit", "-q", "--allow-empty", "-m", "Second change", "-m", "Its body."),
        ("config", "core.hooksPath", ".githooks"),
    ):
        done = made.git(*args)
        assert done.returncode == 0, (args, done.stderr)
    made.oid = made.git("rev-parse", "HEAD").stdout.strip()
    made.set(
        number="7", state="OPEN", head=made.oid, body="", reply=REPLY,
        messages="First change\n\nSecond change\nIts body.\n",
    )  # fmt: skip
    return made


def _template(repo: Repo) -> str:
    return (repo.root / ".github/PULL_REQUEST_TEMPLATE.md").read_text()


def test_an_empty_description_is_filled_in_from_claude_reading_the_pull_request(
    repo: Repo,
) -> None:
    done = repo.fill()

    assert done.returncode == 0
    edited = repo.edited()
    assert edited is not None
    assert edited.startswith(MARKER) and edited.endswith("\n\n" + REPLY)
    assert "filled in #7's description (it was empty)" in done.stdout
    prompt = (repo.state / "prompt").read_text()
    assert "pull request #7" in prompt and f"as of commit {repo.oid}" in prompt
    assert "## Type of change" in prompt  # the template it fills in


def test_claude_can_only_read(repo: Repo) -> None:
    repo.fill()

    args = (repo.state / "claude-args").read_text().splitlines()
    assert args[args.index("--tools") + 1] == "Read,Grep,Glob,Bash"
    allowed = args[args.index("--allowedTools") + 1 : args.index("--permission-mode")]
    assert allowed == [
        "Read", "Grep", "Glob",
        "Bash(gh pr view:*)", "Bash(gh pr diff:*)", "Bash(gh pr checks:*)",
    ]  # fmt: skip
    assert args[args.index("--permission-mode") + 1] == "dontAsk"
    assert "--strict-mcp-config" in args and "--no-session-persistence" in args


@pytest.mark.parametrize(
    ("body", "written"),
    [
        ("TEMPLATE", True),  # as GitHub's form puts it: CRLF, spaces at line ends
        ("- First change\n- Second change\n", True),  # gh pr create --fill, several commits
        ("Second change\n\nIts body.\n", True),  # and its subject and body, as typed
        ("Hand-written context.\n", False),
        ("- First change\n- Also fixes the login page\n", False),  # a line someone added
        ("EDITED TEMPLATE", False),
    ],
)
def test_only_a_description_nobody_wrote_is_filled_in(repo: Repo, body: str, written: bool) -> None:
    template = _template(repo)
    if body == "TEMPLATE":
        body = "\r\n".join(line + "  " for line in template.splitlines()) + "\r\n\r\n"
    elif body == "EDITED TEMPLATE":
        body = template.replace("Closes #123", "Closes #45")
    repo.set(body=body)

    done = repo.fill()

    assert done.returncode == 0
    assert (repo.edited() is not None) is written
    assert (repo.state / "prompt").exists() is written  # claude runs only to write
    if not written:
        assert "written by someone; left alone" in done.stdout


def test_its_own_description_is_rewritten_until_someone_edits_it(repo: Repo) -> None:
    repo.fill()
    repo.set(reply="## Description\n\nAdds the feature, and its tests.\n")

    again = repo.fill()

    assert "(it was this hook's, unedited)" in again.stdout
    assert (repo.edited() or "").endswith("Adds the feature, and its tests.\n")
    edited = (repo.state / "body").read_text().replace("its tests", "its tests and docs")
    repo.set(body=edited)
    (repo.state / "edited").unlink()

    last = repo.fill()

    assert "left alone" in last.stdout and repo.edited() is None


@pytest.mark.parametrize(
    "change",
    [
        'echo 0123456789abcdef0123456789abcdef01234567 >"$state/head"',  # a later push
        'echo MERGED >"$state/state"',
        "echo 'Written meanwhile.' >\"$state/body\"",
    ],
)
def test_a_pull_request_that_changes_while_claude_writes_is_left_alone(
    repo: Repo, change: str
) -> None:
    repo.set(during=f"state={repo.state}\n{change}\n")

    done = repo.fill()

    assert done.returncode == 0 and repo.edited() is None
    assert "changed while its description was written" in done.stdout


def test_without_an_open_pull_request_for_the_commit_nothing_happens(repo: Repo) -> None:
    repo.set(error='no pull requests found for branch "feature"\n')

    missing = repo.fill()

    (repo.state / "error").unlink()
    repo.set(head="0123456789abcdef0123456789abcdef01234567")  # not pushed yet
    behind = repo.fill()

    for done in (missing, behind):
        assert done.returncode == 0
        assert "nothing to fill in" in done.stdout
    assert not (repo.state / "prompt").exists() and repo.edited() is None


@pytest.mark.parametrize(
    ("setup", "said"),
    [
        ({"error": "HTTP 401: Bad credentials\n"}, "gh couldn't look up the pull request"),
        ({"claude-fails": ""}, "claude couldn't write it: boom"),
        ({"reply": "\n  \n"}, "claude wrote nothing"),
    ],
)
def test_a_failure_is_logged_and_changes_nothing(
    repo: Repo, setup: dict[str, str], said: str
) -> None:
    repo.set(**setup)

    done = repo.fill()

    assert done.returncode == 0 and repo.edited() is None
    assert said in done.stdout


def _wait_for(path: Path) -> bool:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.1)
    return False


def test_a_push_returns_at_once_and_the_description_fills_in_behind_it(repo: Repo) -> None:
    repo.set(during="sleep 2\n")  # claude takes a while

    done = repo.git("push", "-q", "origin", "feature")

    assert done.returncode == 0, done.stderr
    assert "Filling in feature's pull request description in the background" in done.stderr
    assert repo.edited() is None  # the push didn't wait for it
    assert _wait_for(repo.state / "edited")
    log = repo.root / ".git/pr-description.log"
    assert _wait_for(log) and "filled in #7's description" in log.read_text()


@pytest.mark.parametrize(
    ("args", "env"),
    [
        (("push", "-q", "origin", "HEAD:main"), {}),  # the default branch has no pull request
        (("push", "-q", "origin", "refs/tags/v1"), {}),
        (("push", "-q", "origin", ":feature"), {}),  # deleting it
        (("push", "-q", "origin", "feature"), {"PR_DESCRIPTION": "0"}),
        (("push", "-q", "origin", "feature"), {"NO_CLAUDE": "1"}),
    ],
)
def test_pushes_it_has_nothing_to_do_for_start_nothing(
    repo: Repo, args: tuple[str, ...], env: dict[str, str]
) -> None:
    assert repo.git("tag", "v1").returncode == 0
    assert repo.git("push", "-q", "--no-verify", "origin", "feature").returncode == 0
    # Something new to push: Git runs no hook for a push that is already up to date
    assert repo.git("commit", "-qn", "--allow-empty", "-m", "Third change").returncode == 0
    if env.pop("NO_CLAUDE", None):
        (Path(repo.env["PATH"].split(":")[0]) / "claude").unlink()
    repo.env.update(env)

    done = repo.git(*args)

    assert done.returncode == 0, done.stderr
    assert "in the background" not in done.stderr
    assert not (repo.root / ".git/pr-description.log").exists()


def test_the_hook_is_executable_and_shellcheck_finds_nothing(repo: Repo) -> None:
    hook = repo.root / ".githooks/pre-push"
    assert hook.stat().st_mode & 0o111
    shellcheck = shutil.which("shellcheck")  # the shellcheck-py dev dependency
    assert shellcheck, "uv sync --dev installs shellcheck"
    done = subprocess.run([shellcheck, "-s", "sh", str(hook)], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout
