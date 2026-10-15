"""Personal adoption: skill packs for one person in a repository they don't manage.

Nothing the repository's other users can see changes. The manifest is .git/repo-template.json,
the links this tool makes are listed in .git/info/exclude (the clone's own ignore file, never
pushed), Claude Code gets the packs' servers in its local scope (~/.claude.json, keyed by this
checkout) and Codex in a .codex/config.toml that Git ignores. A path the repository tracks is
never linked, listed or removed, and a link or Codex block Git would no longer ignore is taken
out again.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from repo_template.mcp_project import BLOCK, CODEX_FILE
from repo_template.model import Result
from repo_template.policies import marked_block_intact, merge_marked_block, remove_marked_block
from repo_template.standards import Paths, git_env, repository_path

EXCLUDE_FILE = ".git/info/exclude"
EXCLUDE_START = "# >>> repo-template personal packs (see .git/repo-template.json)"
EXCLUDE_END = "# <<< repo-template personal packs"
EXCLUDE_LABEL = f"{EXCLUDE_FILE} (personal packs)"
SEGMENT = re.compile(r"[A-Za-z0-9._-]+")  # no character an ignore pattern treats specially


def _git(root: Path, *args: str, stdin: bytes = b"") -> bytes:
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *args],
            input=stdin,
            capture_output=True,
            check=False,
            env=git_env(),
        )
    except FileNotFoundError:
        raise ValueError("personal adoption needs Git, which isn't installed") from None
    if done.returncode not in (0, 1):  # check-ignore exits 1 when it matched nothing
        message = done.stderr.decode(errors="replace").strip()
        raise ValueError(f"git {args[0]} failed in {root}: {message}")
    return done.stdout


def inside(root: Path, path: Path) -> str | None:
    """`path` as a repository path, or None when it resolves outside the repository."""
    try:
        return repository_path(root, path)
    except ValueError:
        return None


def _parents(name: str) -> list[str]:
    parts = name.split("/")
    return ["/".join(parts[:end]) for end in range(1, len(parts))]


class Index:
    """The repository's index: whether it tracks a path, something under it, or something above
    it (the whole index decides, sparse and skip-worktree entries too), compared through any
    symlinked folder, so a skills folder that links elsewhere in the repository is covered."""

    def __init__(self, root: Path) -> None:
        listed = _git(root, "ls-files", "-z")
        self.root = root
        self.entries = {os.fsdecode(item) for item in listed.split(b"\0") if item}
        self.folders = {parent for entry in self.entries for parent in _parents(entry)}

    def __call__(self, path: Path) -> bool:
        name = inside(self.root, path)
        if name is None:
            return False
        return (
            name in self.entries
            or name in self.folders
            or any(parent in self.entries for parent in _parents(name))
        )

    def only_under(self, path: Path) -> bool:
        """Tracked only around the path: as a folder it stands for (files under it, maybe not
        checked out), or under an entry above it (a submodule mounted there). A link of this
        tool's there can't be the repository's version, and it stands in the repository's way."""
        name = inside(self.root, path)
        if name is None or name in self.entries:
            return False
        return name in self.folders or any(parent in self.entries for parent in _parents(name))


def sparse(root: Path) -> bool:
    """Whether the checkout is sparse: then repository files outside its definition aren't on
    disk, and a link or Codex file of this tool's can stand where one of them lands."""
    return _git(root, "config", "--bool", "--get", "core.sparseCheckout").strip() == b"true"


def tracked_paths(root: Path) -> Index:
    return Index(root)


@dataclass(frozen=True)
class Verdict:
    """The pattern that decides whether Git ignores a path (empty: none matches)."""

    source: str
    pattern: str

    @property
    def negated(self) -> bool:
        return self.pattern.startswith("!")

    @property
    def in_tree(self) -> bool:
        """From a .gitignore in the repository: those come before .git/info/exclude."""
        return (
            Path(self.source).name == ".gitignore"
            and not os.path.isabs(self.source)
            and not self.source.startswith(".git/")
        )


def verdicts(root: Path, paths: list[Path]) -> dict[Path, Verdict]:
    """Git's deciding pattern for each path inside the repository, read before anything is
    written."""
    relative = {name: path for path in paths if (name := inside(root, path)) is not None}
    if not relative:
        return {}
    out = _git(
        root, "check-ignore", "-v", "-n", "--stdin", "-z", stdin="\0".join(relative).encode()
    )
    fields = [os.fsdecode(item) for item in out.split(b"\0")]
    found: dict[Path, Verdict] = {}
    for index in range(0, len(fields) - 3, 4):  # source, line, pattern, path
        source, _, pattern, name = fields[index : index + 4]
        if name in relative:
            found[relative[name]] = Verdict(source, pattern)
    return found


def predicted_ignores(root: Path, listed: set[str]) -> Paths:
    """Which paths Git will ignore once the exclude block lists `listed` (repository paths). A
    listed path is ignored unless a .gitignore in the repository decides it (a team's `!`
    pattern beats the block); any other path keeps Git's answer now. Check and update ask the
    same question before anything is written, so they give the same answer."""

    def ignored(paths: list[Path]) -> set[Path]:
        found = set()
        for path, verdict in verdicts(root, paths).items():
            if verdict.in_tree:
                hit = not verdict.negated
            else:
                hit = repository_path(root, path) in listed or (
                    bool(verdict.source) and not verdict.negated
                )
            if hit:
                found.add(path)
        return found

    return ignored


def exclude_patterns(root: Path, links: set[Path], codex: bool, result: Result) -> list[str]:
    """The exclude block: each link this tool has, each followed by a rule that matches only a
    folder there, so a team's skill folder that replaces the link (after a pull) shows again;
    and the Codex file while repo-template's block is in it. A path an ignore pattern would read
    differently isn't listed, so it is linked only where Git ignores it anyway."""
    patterns = []
    for link in sorted(links):
        name = inside(root, link)
        if name is None or not all(SEGMENT.fullmatch(part) for part in name.split("/")):
            result.errors.append(f"{link}: not a path an ignore pattern can list exactly")
            continue
        patterns += [f"/{name}", f"!/{name}/"]
    codex_name = inside(root, root / CODEX_FILE) if codex else None
    if codex_name is not None:  # through a .codex that links elsewhere in the repository too
        folder = codex_name.rsplit("/", 1)[0]
        patterns += [f"/{codex_name}", f"/{folder}/.config.toml.repo-template-tmp"]
    return patterns


def listed_paths(patterns: list[str]) -> set[str]:
    """The repository paths the block ignores."""
    return {pattern[1:] for pattern in patterns if pattern.startswith("/")}


DAMAGED = "repo-template's block has lost a marker line; fix or delete it"
OUTSIDE = "it resolves outside this checkout's .git, so it may be shared; not written"


@dataclass(frozen=True)
class ExcludePlan:
    path: Path
    existing: str
    proposed: str
    damaged: bool  # not written: repo-template's markers are broken, or the file is shared
    why: str = DAMAGED


def plan_exclude(root: Path, patterns: list[str]) -> ExcludePlan:
    """The exclude file with repo-template's block listing `patterns` (none: no block). Raises
    ValueError, before anything is written, for a file that can't be read."""
    path = root / EXCLUDE_FILE
    try:
        existing = path.read_text() if path.exists() else ""
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    git = (root / ".git").resolve()
    if git not in path.resolve().parents:  # through a link to a file or folder elsewhere
        return ExcludePlan(path, existing, existing, damaged=True, why=OUTSIDE)
    if not marked_block_intact(existing, EXCLUDE_START, EXCLUDE_END):
        return ExcludePlan(path, existing, existing, damaged=True)
    if patterns:
        proposed = merge_marked_block(existing, "\n".join(patterns), EXCLUDE_START, EXCLUDE_END)
    else:
        proposed = remove_marked_block(existing, EXCLUDE_START, EXCLUDE_END)
    return ExcludePlan(path, existing, proposed, damaged=False)


def apply_exclude(plan: ExcludePlan, result: Result, *, check: bool) -> None:
    if plan.damaged:
        result.preserved.append(f"{EXCLUDE_FILE} ({plan.why})")
        return
    if plan.proposed == plan.existing:
        if EXCLUDE_START in plan.existing:
            result.unchanged.append(EXCLUDE_LABEL)
        return
    if EXCLUDE_START not in plan.proposed:
        result.removed.append(EXCLUDE_LABEL)
    else:
        (result.updated if EXCLUDE_START in plan.existing else result.created).append(EXCLUDE_LABEL)
    if check:
        return
    target = plan.path.resolve()  # through a link within .git, to the file it names
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.repo-template-tmp")
    temporary.write_text(plan.proposed)
    temporary.replace(target)


def codex_choice(root: Path, tracked: Callable[[Path], bool]) -> tuple[str, str | None]:
    """What personal adoption does with .codex/config.toml: "sync" (repo-template's block goes
    there, ignored), "remove" (take the block out: Git would show the file) or "skip"; and a
    note saying why not. It goes into a file that holds nothing else, or one the repository's
    .gitignore ignores: never into a file of the user's own that only their own rules might
    hide, which the block's line would mask (Git reports one deciding rule)."""
    path = root / CODEX_FILE
    if inside(root, path) is None:
        return "skip", f"{CODEX_FILE} resolves outside this repository; no pack servers for Codex"
    if tracked(path):
        return "skip", f"the repository tracks {CODEX_FILE}; no pack servers for Codex here"
    try:
        text = path.read_text() if path.is_file() and not path.is_symlink() else ""
    except (OSError, UnicodeDecodeError):
        return "skip", f"{CODEX_FILE} can't be read; no pack servers for Codex here"
    found = BLOCK.search(text)
    own = (BLOCK.sub("", text) if found else text).strip()
    verdict = verdicts(root, [path]).get(path, Verdict("", ""))
    if verdict.in_tree and verdict.negated:
        why = f"the repository's .gitignore un-ignores {CODEX_FILE}"
    elif not own or verdict.in_tree:
        return "sync", None
    else:
        why = f"{CODEX_FILE} holds settings of your own the repository doesn't ignore"
    return ("remove" if found else "skip"), f"{why}, so Codex gets no pack servers here"


def team_servers(root: Path) -> set[str]:
    """The servers the repository's own .mcp.json defines; it is read, never written."""
    try:
        document = json.loads((root / ".mcp.json").read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return set()
    servers = document.get("mcpServers") if isinstance(document, dict) else None
    return set(servers) if isinstance(servers, dict) else set()
