"""Walk the person through every file update preserved: compare it, then decide.

For a file that differs from the baseline the choices are: use the baseline, keep yours (asked
again only when the baseline's version changes), merge change by change, always keep yours (the
file becomes project-owned), or skip. A file under an old name (CONTEXT.md, CLAUDE.md) can be
moved to its new name. Every decision is applied, and recorded in the manifest, as it is made.
"""

from __future__ import annotations

import difflib
import os
import sys
from collections.abc import Sequence
from difflib import SequenceMatcher
from pathlib import Path
from typing import Protocol

from repo_template.model import Conflict
from repo_template.repository import Runner
from repo_template.scaffold import accept_difference, own_file, write_file

Options = Sequence[tuple[str, str]]

FILE_CHOICES: Options = (
    ("o", "use the baseline"),
    ("k", "keep yours"),
    ("m", "merge change by change"),
    ("a", "always keep yours"),
    ("s", "skip for now"),
)
MOVE_CHOICES: Options = (("m", "move it now"), ("s", "skip for now"))
MAX_REFERENCES = 10


class Prompt(Protocol):
    """Talks to the person. The terminal in production; scripted answers in tests."""

    def say(self, text: str = "") -> None: ...

    def diff(self, lines: Sequence[str]) -> None: ...

    def choose(self, question: str, options: Options) -> str: ...


class TerminalPrompt:
    def __init__(self) -> None:
        self.color = sys.stdout.isatty() and "NO_COLOR" not in os.environ

    def say(self, text: str = "") -> None:
        print(text)

    def diff(self, lines: Sequence[str]) -> None:
        for line in lines:
            line = line.rstrip("\n")
            if self.color and line.startswith(("+++", "---")):
                line = f"\033[1m{line}\033[0m"
            elif self.color and line.startswith("+"):
                line = f"\033[32m{line}\033[0m"
            elif self.color and line.startswith("-"):
                line = f"\033[31m{line}\033[0m"
            elif self.color and line.startswith("@@"):
                line = f"\033[36m{line}\033[0m"
            print(f"    {line}")

    def choose(self, question: str, options: Options) -> str:
        keys = "/".join(key for key, _ in options)
        menu = "  ".join(f"[{key}] {label}" for key, label in options)
        while True:
            print(f"  {menu}")
            try:
                answer = input(f"  {question} [{keys}]? ").strip().lower()
            except EOFError:
                print()
                return "s"
            if any(answer == key for key, _ in options):
                return answer


def _merge(existing: str, desired: str, prompt: Prompt) -> str:
    """Build a file from the person's choice at each place yours and the baseline's differ."""
    ours, theirs = existing.splitlines(keepends=True), desired.splitlines(keepends=True)
    merged: list[str] = []
    changes = [op for op in SequenceMatcher(None, ours, theirs, autojunk=False).get_opcodes()]
    total = sum(1 for tag, *_ in changes if tag != "equal")
    number = 0
    for tag, i1, i2, j1, j2 in changes:
        if tag == "equal":
            merged.extend(ours[i1:i2])
            continue
        number += 1
        context = [f" {line}" for line in ours[max(0, i1 - 2) : i1]]
        removed = [f"-{line}" for line in ours[i1:i2]]
        added = [f"+{line}" for line in theirs[j1:j2]]
        prompt.say(f"  Change {number} of {total}:")
        prompt.diff([*context, *removed, *added])
        if tag == "insert":
            options: Options = (("y", "add the baseline's lines"), ("n", "leave them out"))
        elif tag == "delete":
            options = (("y", "remove your lines"), ("n", "keep your lines"))
        else:
            options = (("y", "take the baseline's"), ("n", "keep yours"), ("b", "keep both"))
        answer = prompt.choose("This change", options)
        if answer == "y":
            merged.extend(theirs[j1:j2])
        elif answer == "b":
            merged.extend([*ours[i1:i2], *theirs[j1:j2]])
        else:
            merged.extend(ours[i1:i2])
    return "".join(merged)


def _references(root: Path, name: str, runner: Runner) -> list[str]:
    if not (root / ".git").exists() or not runner.which("git"):
        return []
    found = runner.run(["git", "grep", "-n", "-I", "-F", "-e", name], root)
    return found.out.splitlines() if found.code == 0 else []


def _move(root: Path, conflict: Conflict, prompt: Prompt, runner: Runner) -> str:
    old, new = conflict.path, str(conflict.moves_to)
    if (root / new).exists():
        prompt.say(f"  {new} already exists: move what you need from {old} into it by hand.")
        return "skipped"
    tracked = (
        (root / ".git").exists()
        and runner.which("git")
        and runner.run(["git", "ls-files", "--error-unmatch", old], root).code == 0
    )
    if tracked:
        done = runner.run(["git", "mv", old, new], root)
        if done.code:
            prompt.say(f"  git mv failed: {done.err.strip()}")
            return "skipped"
    else:
        os.replace(root / old, root / new)
    if conflict.legacy_baseline is not None:
        write_file(root, old, conflict.legacy_baseline)
        prompt.say(f"  Moved {old} to {new}; {old} now holds the baseline's version.")
    else:
        prompt.say(f"  Moved {old} to {new}.")
    references = _references(root, old, runner)
    if references:
        prompt.say(f"  These lines still mention {old}:")
        for line in references[:MAX_REFERENCES]:
            prompt.say(f"    {line}")
        if len(references) > MAX_REFERENCES:
            prompt.say(f"    … and {len(references) - MAX_REFERENCES} more")
    return "moved (staged with git mv)" if tracked else "moved"


def _decide_file(root: Path, conflict: Conflict, prompt: Prompt) -> str:
    lines = list(
        difflib.unified_diff(
            conflict.existing.splitlines(keepends=True),
            conflict.desired.splitlines(keepends=True),
            fromfile=f"yours/{conflict.path}",
            tofile=f"baseline/{conflict.path}",
        )
    )
    prompt.diff(lines)
    answer = prompt.choose("Your choice", FILE_CHOICES)
    if answer == "o":
        write_file(root, conflict.path, conflict.desired, executable=conflict.executable)
        return "used the baseline"
    if answer == "k":
        accept_difference(root, conflict.path, conflict.existing, conflict.desired)
        return "kept yours"
    if answer == "a":
        own_file(root, conflict.path)
        return "always keep yours"
    if answer == "m":
        merged = _merge(conflict.existing, conflict.desired, prompt)
        if merged == conflict.desired:
            write_file(root, conflict.path, merged, executable=conflict.executable)
            return "used the baseline"
        if merged != conflict.existing:
            write_file(root, conflict.path, merged, executable=conflict.executable)
        accept_difference(root, conflict.path, merged, conflict.desired)
        return "merged"
    return "skipped"


def resolve_conflicts(
    root: Path, conflicts: Sequence[Conflict], prompt: Prompt, runner: Runner
) -> list[tuple[str, str]]:
    """Ask about each conflict in turn and apply the answer. Returns (path, outcome) pairs."""
    outcomes: list[tuple[str, str]] = []
    prompt.say(
        f"{len(conflicts)} file(s) differ from the baseline. For each one: use the baseline, "
        "keep yours (asked again only if the baseline's version changes), merge change by "
        "change, always keep yours (never asked again), or skip."
    )
    for number, conflict in enumerate(conflicts, start=1):
        prompt.say()
        if conflict.moves_to:
            prompt.say(f"[{number}/{len(conflicts)}] {conflict.path} is now {conflict.moves_to}")
            prompt.say(f"  {conflict.reason}")
            answer = prompt.choose("Move it", MOVE_CHOICES)
            outcome = _move(root, conflict, prompt, runner) if answer == "m" else "skipped"
        else:
            reason = f" ({conflict.reason})" if conflict.reason else ""
            prompt.say(f"[{number}/{len(conflicts)}] {conflict.path}{reason}")
            outcome = _decide_file(root, conflict, prompt)
        outcomes.append((conflict.path, outcome))
    staged = [path for path, outcome in outcomes if outcome == "moved (staged with git mv)"]
    if staged:
        prompt.say()
        prompt.say(
            "To keep the moved files' history, commit the staged moves on their own before "
            f'staging anything else: git commit -m "Move {", ".join(staged)} to their new names"'
        )
    return outcomes
