"""The catalog against its upstream repositories, over the network.

`globals --upstream` reports what changed upstream and writes nothing. `globals --upgrade`
vendors skills, refreshing or adding them: each is fetched into a staging folder, verified
against the upstream tree SHA (from the listing and again from the bytes on disk), scanned with
the committed skill-scanner, shown as a diff, and only then swapped in. The swap and its record
writes are one journaled transaction: an error, a signal or a kill at any point before it
completes rolls back to the state before it. Everything else in repo-template works offline.
"""

from __future__ import annotations

import base64
import difflib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import textwrap
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import FrameType, TracebackType
from typing import Any, Protocol

from repo_template.catalog import (
    LICENSE_FILE,
    LICENSES_DIR,
    LOCK_NAME,
    OVERRIDES_NAME,
    PACKS_DIR,
    PACKS_NAME,
    SHA,
    SKILLS_DIR,
    SOURCES_NAME,
    STAGE_PREFIX,
    blob_sha,
    folder_tree,
    load_commands,
    override,
    own_license,
    read_skill,
    runs_on_load,
    upstream_skill_md,
    upstream_url,
)
from repo_template.model import Result
from repo_template.resolve import Options, Prompt, visible
from repo_template.skillfile import field_lines, read_fields

SOURCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}")
NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
REF = re.compile(r"[A-Za-z0-9._][A-Za-z0-9._/-]{0,99}")
FOLDER = re.compile(r"[A-Za-z0-9._@+-]+(?:/[A-Za-z0-9._@+-]+)*")  # an upstream skill folder
URL = re.compile(r"https?://[^\s<>\"'`)\]}]+")
RESERVED = {"synced"}  # names skill_names() skips
MAX_FILES = 2000
MAX_BYTES = 20 * 1024 * 1024
DIFF_LINES = 400
PREVIOUS = "previous"  # the live copy a swap replaces, kept until the swap completes
GIT_FILES = {".gitignore", ".gitattributes", ".gitmodules"}  # would change how Git sees the skill
CODE_SUFFIXES = {".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl", ".ps1"}
QUIET_FIELDS = {"name", "description", "license", "metadata", "version"}  # not permissions
SEVERITIES = ("critical", "high", "medium", "low", "info")
BLOCKING = ("critical", "high")
COPYRIGHT = re.compile(
    r"^[ \t]*(?:Portions[ \t]+)?Copyright\b[^\n]*$"  # a line that starts with it, or
    r"|^[^\n]*\b(?i:copyright)[ \t]*(?:\((?i:c)\)|©|\d{4})[^\n]*$",  # "(c)", "©" or a year
    re.M,
)
NOT_A_HOLDER = re.compile(
    r"(?i)copyright[ \t]+(?:notice|owner|holder|license|statement|and|law|act|treaty|"
    r"protection|interest)"
)


class NetworkError(Exception):
    """GitHub couldn't be reached or refused a request: exit 3."""


class NotFound(NetworkError):
    """GitHub answered 404: that repository, ref or path isn't there (any more)."""


class _Interrupted(BaseException):
    """SIGTERM or SIGHUP, raised so every cleanup and rollback still runs."""


def clean(text: str) -> str:
    """Upstream text made safe to print: no control characters, and no line that a GitHub
    Actions runner would read as a workflow command (it strips leading whitespace first)."""
    text = "".join(char if char.isprintable() else "?" for char in text)
    return "\\" + text if text.lstrip().startswith("::") else text


# GitHub, behind a protocol so tests can serve fake repositories.


@dataclass(frozen=True)
class Entry:
    path: str
    mode: str  # 100644, 100755, 040000, or anything a vendored skill may not hold
    sha: str
    size: int = 0


class GitHub(Protocol):
    def commit(self, source: str, ref: str) -> tuple[str, str]:
        """(commit SHA, root tree SHA) for a ref."""
        ...

    def tree(self, source: str, sha: str, *, recursive: bool) -> tuple[list[Entry], bool]:
        """A tree's entries, and whether GitHub truncated the listing."""
        ...

    def blob(self, source: str, sha: str) -> bytes: ...

    def license(self, source: str) -> str | None:
        """The SPDX id GitHub detects for the repository's license; None if it has none."""
        ...

    def latest_release(self, source: str) -> str | None:
        """The tag of the latest release; None if there are no releases."""
        ...

    def is_tag(self, source: str, ref: str) -> bool: ...


class GhApi:
    """The GitHub REST API through `gh api` (its login, telemetry off), else urllib with
    $GH_TOKEN."""

    def _get(self, path: str) -> Any:
        if shutil.which("gh"):
            try:
                done = subprocess.run(
                    ["gh", "api", "-H", "Accept: application/vnd.github+json", path],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                    env={**os.environ, "GH_TELEMETRY": "0", "GH_NO_UPDATE_NOTIFIER": "1"},
                )
            except subprocess.TimeoutExpired:
                raise NetworkError(f"gh api {path} timed out") from None
            if done.returncode:
                error = NotFound if "HTTP 404" in done.stderr else NetworkError
                raise error(f"gh api {path}: {clean(done.stderr.strip()[:300])}")
            return json.loads(done.stdout)
        request = urllib.request.Request(
            f"https://api.github.com/{path}", headers={"Accept": "application/vnd.github+json"}
        )
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            error = NotFound if exc.code == 404 else NetworkError
            raise error(f"GET {path}: HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise NetworkError(f"GET {path}: {clean(str(exc))}") from None

    def commit(self, source: str, ref: str) -> tuple[str, str]:
        data = self._get(f"repos/{source}/commits/{urllib.parse.quote(ref, safe='')}")
        try:
            return str(data["sha"]), str(data["commit"]["tree"]["sha"])
        except (KeyError, TypeError):
            raise NetworkError(f"{source}@{ref}: unexpected commit data") from None

    def tree(self, source: str, sha: str, *, recursive: bool) -> tuple[list[Entry], bool]:
        data = self._get(f"repos/{source}/git/trees/{sha}" + ("?recursive=1" if recursive else ""))
        try:
            entries = [
                Entry(item["path"], item["mode"], item["sha"], int(item.get("size") or 0))
                for item in data.get("tree", [])
            ]
        except (KeyError, TypeError, ValueError):
            raise NetworkError(f"{source}: unexpected tree data for {sha}") from None
        return entries, bool(data.get("truncated"))

    def blob(self, source: str, sha: str) -> bytes:
        data = self._get(f"repos/{source}/git/blobs/{sha}")
        if not isinstance(data, dict) or data.get("encoding") != "base64":
            raise NetworkError(f"blob {sha} of {source} didn't come back base64-encoded")
        return base64.b64decode(data["content"])

    def license(self, source: str) -> str | None:
        try:
            data = self._get(f"repos/{source}/license")
        except NotFound:
            return None
        spdx = (data.get("license") or {}).get("spdx_id")
        return spdx if isinstance(spdx, str) else None

    def latest_release(self, source: str) -> str | None:
        try:
            data = self._get(f"repos/{source}/releases/latest")
        except NotFound:
            return None
        tag = data.get("tag_name")
        return tag if isinstance(tag, str) else None

    def is_tag(self, source: str, ref: str) -> bool:
        try:
            self._get(f"repos/{source}/git/ref/tags/{urllib.parse.quote(ref, safe='/')}")
        except NotFound:
            return False
        return True


class Snapshot:
    """One source at one ref: its commit, and folder lookups that share cached trees."""

    def __init__(self, github: GitHub, source: str, ref: str) -> None:
        self.github, self.source, self.ref = github, source, ref
        self.commit, self.root = github.commit(source, ref)
        self._trees: dict[str, list[Entry]] = {}
        entries, truncated = github.tree(source, self.root, recursive=True)
        self.everything: dict[str, Entry] | None = (
            None if truncated else {entry.path: entry for entry in entries}
        )

    def _children(self, sha: str) -> list[Entry]:
        if sha not in self._trees:
            self._trees[sha] = self.github.tree(self.source, sha, recursive=False)[0]
        return self._trees[sha]

    def entry(self, path: str) -> Entry | None:
        if self.everything is not None:
            return self.everything.get(path)
        sha, found = self.root, None
        for part in path.split("/"):
            found = next((e for e in self._children(sha) if e.path == part), None)
            if found is None:
                return None
            sha = found.sha
        return None if found is None else Entry(path, found.mode, found.sha, found.size)

    def folder(self, path: str) -> str | None:
        found = self.entry(path)
        return found.sha if found and found.mode == "040000" else None

    def skill_folders(self) -> dict[str, list[str]] | None:
        """{folder name: [paths]} of every folder holding a SKILL.md; None if truncated."""
        if self.everything is None:
            return None
        folders: dict[str, list[str]] = {}
        for path in self.everything:
            if path == "SKILL.md" or not path.endswith("/SKILL.md"):
                continue
            folder = path.rsplit("/", 1)[0]
            folders.setdefault(folder.rsplit("/", 1)[-1], []).append(folder)
        return folders

    def text(self, path: str) -> str | None:
        found = self.entry(path)
        if found is None or found.mode not in {"100644", "100755"}:
            return None
        data = self.github.blob(self.source, found.sha)
        return data.decode(errors="replace") if blob_sha(data) == found.sha else None

    def moved(self, name: str, old_folder: str) -> list[str] | None:
        """Where a skill that left `old_folder` is now: folders named after it or after its old
        folder whose SKILL.md names it. None when the tree is too large to say."""
        folders = self.skill_folders()
        if folders is None:
            return None
        basename = old_folder.rsplit("/", 1)[-1]
        candidates = sorted({*folders.get(name, []), *folders.get(basename, [])})
        found = []
        for folder in candidates:
            text = self.text(f"{folder}/SKILL.md")
            with suppress(ValueError):
                if text is not None and read_fields(text).get("name") == name:
                    found.append(folder)
        return found


Snapshots = Callable[[str, str], Snapshot]


def _snapshots(github: GitHub) -> Snapshots:
    cache: dict[tuple[str, str], Snapshot] = {}

    def snapshot(source: str, ref: str) -> Snapshot:
        if (source, ref) not in cache:
            cache[(source, ref)] = Snapshot(github, source, ref)
        return cache[(source, ref)]

    return snapshot


def _json(root: Path, name: str) -> Any:
    return json.loads((root / name).read_text())


def _folder(lock_entry: dict[str, Any]) -> str:
    return str(lock_entry.get("skillPath", "")).rsplit("/", 1)[0]


def _ref(sources: dict[str, Any], name: str) -> str:
    return str(sources.get("skills", {}).get(name, {}).get("ref") or "HEAD")


def _stale_override(
    record: dict[str, Any], new_upstream: str | None, fields: dict[str, Any]
) -> list[str]:
    """The overridden fields whose upstream text changed: the override needs another look."""
    base = record.get("base") if isinstance(record.get("base"), dict) else {}
    if new_upstream is None or not isinstance(base, dict):
        return []
    try:
        return [
            key for key in fields if key in base and field_lines(new_upstream, key) != base[key]
        ]
    except ValueError:
        return list(fields)


def _license_changes(sources: dict[str, Any], source: str, upstream: Snapshot) -> list[str]:
    """Each pinned license file of a source that is gone or changed at this snapshot."""
    record = sources.get("sources", {}).get(source, {})
    changes = []
    for file, pinned in sorted((record.get("licenseFiles") or {}).items()):
        found = upstream.entry(file)
        if found is None:
            changes.append(f"its {file} is gone upstream")
        elif found.sha != pinned:
            changes.append(f"its {file} changed upstream")
    return changes


# globals --upstream


@dataclass
class Report:
    current: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    review: list[str] = field(default_factory=list)  # removed, moved, licenses, stale records
    new: list[str] = field(default_factory=list)  # informational
    notes: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 2 if self.review else (1 if self.changed else 0)


def upstream_report(root: Path, github: GitHub) -> Report:
    """Compare every vendored skill and license text with upstream. Writes nothing."""
    lock = _json(root, LOCK_NAME).get("skills", {})
    sources = _json(root, SOURCES_NAME)
    overrides = _json(root, OVERRIDES_NAME) if (root / OVERRIDES_NAME).is_file() else {}
    report = Report()
    snapshot = _snapshots(github)
    for name in sorted(lock):
        try:
            _report_skill(report, name, lock[name], sources, overrides, github, snapshot)
        except NotFound as exc:
            report.review.append(f"{name}: not upstream any more (deleted or renamed?): {exc}")
    in_use = {(lock[name]["source"], _ref(sources, name)) for name in lock}
    vendored = {(entry["source"], _folder(entry)) for entry in lock.values()}
    for source, record in sorted(sources.get("sources", {}).items()):
        refs = sorted(ref for used, ref in in_use if used == source) or ["HEAD"]
        try:
            upstream = snapshot(source, refs[0])
        except NotFound as exc:
            report.review.append(f"{source}: not upstream any more: {exc}")
            continue
        for change in _license_changes(sources, source, upstream):
            report.review.append(f"{source}: {change}; check the license")
        if record.get("discover") != "all":
            continue
        folders = upstream.skill_folders()
        if folders is None:
            report.notes.append(f"{source}: tree too large to list its new skills")
            continue
        skipped = set(sources.get("ignored", {}).get(source, {}))
        for name in sorted(set(folders) - set(lock) - skipped):
            paths = [path for path in folders[name] if (source, path) not in vendored]
            if NAME.fullmatch(name) and paths and all(FOLDER.fullmatch(path) for path in paths):
                shown = ", ".join(paths)
                report.new.append(f"{name}: new in {source} ({shown}); add {source}@{name}")
    return report


def _report_skill(
    report: Report,
    name: str,
    entry: dict[str, Any],
    sources: dict[str, Any],
    overrides: dict[str, Any],
    github: GitHub,
    snapshot: Snapshots,
) -> None:
    source, ref, folder = entry["source"], _ref(sources, name), _folder(entry)
    upstream = snapshot(source, ref)
    sha = upstream.folder(folder)
    at = f"{source}@{ref} ({upstream.commit[:12]})"
    if sha == entry.get("skillFolderHash"):
        report.current.append(name)
    elif sha is not None:
        report.changed.append(f"{name}: changed in {at}")
        if name in overrides:
            fields = overrides[name].get("frontmatter", {})
            new = upstream.text(f"{folder}/SKILL.md")
            for key in _stale_override(overrides[name], new, fields):
                report.review.append(
                    f"{name}: upstream changed its {key!r}, which an override replaces; "
                    f"review the override"
                )
    else:
        moved = upstream.moved(name, folder)
        if moved:
            report.review.append(f"{name}: moved to {clean(', '.join(moved))} in {at}")
        elif moved is None:
            report.review.append(f"{name}: not at {folder} in {at}; it may have moved")
        else:
            report.review.append(f"{name}: removed from {at}; remove it or keep it")
    if ref != "HEAD" and not SHA.fullmatch(ref) and github.is_tag(source, ref):
        latest = github.latest_release(source)
        if latest and latest != ref:
            report.changed.append(
                f"{name}: pinned at {clean(ref)}; {clean(latest)} is out; re-pin it with "
                f"`globals --upgrade {source}@{folder}#{clean(latest)}`"
            )
    recorded = sources.get("skills", {}).get(name, {}).get("commit")
    if isinstance(recorded, str) and recorded != upstream.commit:
        try:
            held = snapshot(source, recorded).folder(folder)
        except NotFound:
            report.review.append(f"{name}: its recorded commit {recorded[:12]} isn't upstream")
            return
        if held != entry.get("skillFolderHash"):
            report.review.append(
                f"{name}: its recorded commit {recorded[:12]} doesn't hold the vendored "
                f"folder; record the commit it came from in {SOURCES_NAME}"
            )


# globals --upgrade: scanning


@dataclass
class Scan:
    counts: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    read: frozenset[str] | None = None  # the files the scanner read, when it says
    untrusted_urls: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def summary(self) -> str:
        if self.error:
            return f"scan failed: {self.error}"
        if not self.total:
            return "scan clean"
        return "scan: " + ", ".join(
            f"{self.counts[s]} {s}" for s in SEVERITIES if self.counts.get(s)
        )


class Scanner(Protocol):
    def scan(self, folder: Path) -> Scan: ...


def scanned(path: str) -> bool:
    """Whether skill-scanner (as committed) reads a file, judged by its rules: SKILL.md,
    references/*.md and scripts/*.{py,sh,js,ts} at the top of those folders. Used when the
    scanner doesn't list what it read."""
    parts = PurePosixPath(path).parts
    if parts == ("SKILL.md",):
        return True
    if len(parts) != 2:
        return False
    suffix = PurePosixPath(parts[1]).suffix
    if parts[0] == "references":
        return suffix == ".md"
    return parts[0] == "scripts" and suffix in {".py", ".sh", ".js", ".ts"}


class HeadScanner:
    """skill-scanner as committed at HEAD, never the copy an upgrade is replacing, run by uv
    from an empty directory with its dependencies pinned to that commit's date. Use it as a
    context manager: it removes its copy when done."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._copy: tempfile.TemporaryDirectory[str] | None = None
        self._date = ""

    def __enter__(self) -> HeadScanner:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._copy is not None:
            self._copy.cleanup()
            self._copy = None

    def _script(self) -> Path:
        folder = ".agents/skills/skill-scanner"
        if self._copy is None:
            self._copy = tempfile.TemporaryDirectory(prefix="repo-template-scanner-")
            copy = Path(self._copy.name)
            listing = _git(self.root, "ls-tree", "-r", "-z", "HEAD", "--", folder)
            for record in filter(None, listing.split(b"\0")):
                meta, _, raw = record.partition(b"\t")
                target = copy / os.fsdecode(raw)[len(folder) + 1 :]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(_git(self.root, "cat-file", "blob", meta.split()[2].decode()))
            log = _git(self.root, "log", "-1", "--format=%cI", "HEAD", "--", folder)
            self._date = log.decode().strip()
        return Path(self._copy.name) / "scripts/scan_skill.py"

    def scan(self, folder: Path) -> Scan:
        uv = shutil.which("uv")
        if uv is None:
            return Scan(error="uv is not installed")
        try:
            script = self._script()
        except ValueError as exc:
            return Scan(error=str(exc))
        if not script.is_file() or not self._date:
            return Scan(error="skill-scanner isn't committed at HEAD")
        command = [uv, "run", "-q", "--no-config", "--exclude-newer", self._date, "--script"]
        with tempfile.TemporaryDirectory() as empty:
            try:
                done = subprocess.run(
                    [*command, str(script), str(folder)],
                    cwd=empty,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return Scan(error="timed out")
        try:
            report = json.loads(done.stdout)
            counts = report["finding_counts"]
        except (json.JSONDecodeError, KeyError, TypeError):
            last = clean(done.stderr.strip().splitlines()[-1] if done.stderr.strip() else "")
            return Scan(error=f"exit {done.returncode}, no report: {last[:300]}")
        if done.returncode or not isinstance(counts, dict):
            return Scan(error=f"exit {done.returncode}")
        structure = report.get("structure") if isinstance(report.get("structure"), dict) else {}
        read: frozenset[str] | None = None
        if isinstance(structure.get("reference_files"), list):
            read = frozenset(
                ["SKILL.md"]
                + [f"references/{name}" for name in structure.get("reference_files", [])]
                + [f"scripts/{name}" for name in structure.get("script_files", [])]
            )
        urls = report.get("urls") if isinstance(report.get("urls"), dict) else {}
        untrusted = tuple(str(url) for url in urls.get("untrusted", []) or [])
        return Scan({str(key): int(value) for key, value in counts.items()}, None, read, untrusted)


def _git(root: Path, *args: str, stdin: bytes | None = None) -> bytes:
    done = subprocess.run(
        ["git", "-C", str(root), *args], input=stdin, capture_output=True, check=False
    )
    if done.returncode:
        raise ValueError(f"git {args[0]} failed: {done.stderr.decode().strip()}")
    return done.stdout


# globals --upgrade: targets and staging


@dataclass(frozen=True)
class Target:
    name: str
    source: str
    folder: str  # in the source repository
    ref: str
    adding: bool


def parse_spec(spec: str) -> tuple[str, str, str] | None:
    """`owner/repo@skill-or-path[#ref]` as (source, skill or path, ref); None for a bare name."""
    if "@" not in spec:
        return None
    source, _, rest = spec.partition("@")
    skill, _, ref = rest.partition("#")
    ref = ref or "HEAD"
    if not SOURCE.fullmatch(source):
        raise ValueError(f"{spec!r}: expected owner/repo@skill[#ref]")
    if not REF.fullmatch(ref) or ".." in ref:
        raise ValueError(f"{spec!r}: {ref!r} isn't a branch, tag or commit name")
    if not skill or not FOLDER.fullmatch(skill) or any(p in {".", ".."} for p in skill.split("/")):
        raise ValueError(f"{spec!r}: name the skill, or its folder in {source}")
    return source, skill, ref


def _safe_path(path: str) -> bool:
    parts = path.split("/")
    return all(
        part not in {"", ".", ".."}
        and part.lower() != ".git"
        and "\\" not in part
        and all(char.isprintable() for char in part)
        for part in parts
    )


def _git_file(path: str) -> bool:
    """A .gitignore, .gitattributes or .gitmodules, in any case and with the trailing dots or
    spaces that Windows ignores."""
    return path.rsplit("/", 1)[-1].rstrip(". ").casefold() in GIT_FILES


@dataclass
class Staged:
    target: Target
    commit: str
    folder_sha: str
    path: Path | None  # None when only the records change (the same files, moved or re-pinned)
    scan: Scan = field(default_factory=Scan)


def _disk_tree(folder: Path) -> str:
    """The git tree SHA of a folder as it is on disk."""
    files = {}
    for path in folder.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        executable = path.stat().st_mode & stat.S_IXUSR
        files[path.relative_to(folder).as_posix()] = (
            "100755" if executable else "100644",
            blob_sha(path.read_bytes()),
        )
    return folder_tree(files)


def stage(github: GitHub, upstream: Snapshot, target: Target, into: Path) -> Staged:
    """Fetch a skill folder into `into`, refusing anything a vendored skill may not hold, and
    verify it hashes to the upstream tree, from the listing and from the files written."""
    sha = upstream.folder(target.folder)
    if sha is None:
        raise ValueError(f"{target.name}: {target.folder} isn't in {target.source}@{target.ref}")
    entries, truncated = github.tree(target.source, sha, recursive=True)
    blobs = [entry for entry in entries if entry.mode != "040000"]
    if truncated or len(blobs) > MAX_FILES:
        raise ValueError(f"{target.name}: more than {MAX_FILES} files")
    if sum(entry.size for entry in blobs) > MAX_BYTES:
        raise ValueError(f"{target.name}: more than {MAX_BYTES // 2**20} MB")
    seen: dict[str, str] = {}
    for entry in entries:
        if entry.mode not in {"100644", "100755", "040000"}:
            raise ValueError(
                f"{target.name}: {clean(entry.path)} is a symlink or submodule (mode "
                f"{clean(entry.mode)}); a vendored skill holds regular files"
            )
        if not _safe_path(entry.path):
            raise ValueError(f"{target.name}: unsafe path {clean(entry.path)!r}")
        if _git_file(entry.path):
            raise ValueError(f"{target.name}: {clean(entry.path)} would change how Git sees it")
        folded = unicodedata.normalize("NFC", entry.path).casefold()
        if folded in seen:
            raise ValueError(
                f"{target.name}: {clean(entry.path)} and {clean(seen[folded])} are one file on "
                f"a case-insensitive file system"
            )
        seen[folded] = entry.path
    if "SKILL.md" not in {entry.path for entry in blobs}:
        raise ValueError(f"{target.name}: {target.folder} has no SKILL.md")
    for entry in blobs:
        data = github.blob(target.source, entry.sha)
        if blob_sha(data) != entry.sha:
            raise ValueError(f"{target.name}: {clean(entry.path)} doesn't match its blob SHA")
        file = into / entry.path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
        file.chmod(0o755 if entry.mode == "100755" else 0o644)
    files = {entry.path: (entry.mode, entry.sha) for entry in blobs}
    if folder_tree(files) != sha or _disk_tree(into) != sha:
        raise ValueError(f"{target.name}: the fetched files don't hash to upstream's tree {sha}")
    return Staged(target, upstream.commit, sha, into)


# globals --upgrade: the review


def _executable(path: Path) -> bool:
    return bool(path.stat().st_mode & stat.S_IXUSR)


def _content(path: Path, replaced: str | None = None) -> tuple[list[str] | None, bytes]:
    """(text lines, or None if binary; raw bytes) of a file, or of `replaced` instead. A NUL
    byte alone doesn't make code binary: shells run a script past one."""
    data = replaced.encode() if replaced is not None else path.read_bytes()
    code = (
        data.startswith(b"#!")
        or PurePosixPath(path.name).suffix in CODE_SUFFIXES
        or (replaced is None and _executable(path))
    )
    if b"\0" in data and not code:
        return None, data
    return data.decode(errors="replace").splitlines(keepends=True), data


def _files(folder: Path | None, only: set[str] | None = None) -> dict[str, Path]:
    if folder is None or not folder.is_dir():
        return {}
    found = {
        path.relative_to(folder).as_posix(): path
        for path in folder.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    return found if only is None else {key: path for key, path in found.items() if key in only}


def _home(root: Path, name: str) -> str:
    """The folder a skill belongs in: .agents/packs when a pack lists it, else .agents/skills."""
    path = root / PACKS_NAME
    try:
        packs = json.loads(path.read_text()) if path.is_file() else {}
    except json.JSONDecodeError:
        packs = {}
    listed = any(
        isinstance(pack, dict) and name in pack.get("skills", []) for pack in packs.values()
    )
    return PACKS_DIR if listed else SKILLS_DIR


def _tracked(root: Path, name: str) -> set[str]:
    """The files Git tracks in a skill: the live side of a review, not the caches its scripts
    leave there."""
    prefix = f"{_home(root, name)}/{name}/"
    listing = _git(root, "ls-files", "-z", "--", prefix)
    return {os.fsdecode(path)[len(prefix) :] for path in listing.split(b"\0") if path}


@dataclass
class Diff:
    changed: list[str] = field(default_factory=list)  # paths whose content or mode differs
    summary: list[str] = field(default_factory=list)  # one line per changed file
    lines: list[str] = field(default_factory=list)  # the whole diff, terminal-safe
    escaped: list[str] = field(default_factory=list)  # files with control characters
    binary: list[str] = field(default_factory=list)  # changed files shown only as binary
    new_urls: list[str] = field(default_factory=list)


def folder_diff(
    current: Path,
    staged: Path,
    name: str,
    replaced: dict[str, str] | None = None,
    live: set[str] | None = None,
) -> Diff:
    """What a swap changes. `replaced` gives the text to compare a current file as (an
    overridden SKILL.md's upstream original, so the diff shows what upstream changed); `live`
    limits the current side to the files Git tracks."""
    replaced = replaced or {}
    before, after = _files(current, live), _files(staged)
    diff = Diff()
    old_urls: set[str] = set()
    new_urls: set[str] = set()
    for path in sorted(set(before) | set(after)):
        old_lines, old_bytes = (
            _content(before[path], replaced.get(path)) if path in before else ([], b"")
        )
        new_lines, new_bytes = _content(after[path]) if path in after else ([], b"")
        old_urls.update(URL.findall("".join(old_lines or [])))
        new_urls.update(URL.findall("".join(new_lines or [])))
        old_mode = _executable(before[path]) if path in before else None
        new_mode = _executable(after[path]) if path in after else None
        if old_bytes == new_bytes and old_mode == new_mode:
            continue
        diff.changed.append(path)
        status = "added" if path not in before else "deleted" if path not in after else "changed"
        mode = (" (now executable)" if new_mode and old_mode is False else "") + (
            " executable" if new_mode and path not in before else ""
        )
        if old_lines is None or new_lines is None:
            diff.binary.append(path)
            diff.summary.append(f"{status}{mode}, binary: {name}/{path}")
            diff.lines.append(f"Binary file {name}/{path} {status}\n")
            continue
        body = list(
            difflib.unified_diff(old_lines, new_lines, f"a/{name}/{path}", f"b/{name}/{path}")
        )
        ended = [line if line.endswith("\n") else line + "\n" for line in body]
        shown = [visible(line) for line in ended]
        if shown != ended:
            diff.escaped.append(path)
        plus = sum(1 for line in body if line.startswith("+") and not line.startswith("+++"))
        minus = sum(1 for line in body if line.startswith("-") and not line.startswith("---"))
        diff.summary.append(f"{status}{mode}: {name}/{path} (+{plus} -{minus})")
        diff.lines += shown
    diff.new_urls = sorted(new_urls - old_urls)
    return diff


def _frontmatter_changes(old: str | None, new: str) -> list[str]:
    """Frontmatter fields, other than the descriptive ones, that the new SKILL.md adds,
    removes or changes: they decide what the skill may do."""
    try:
        before = read_fields(old) if old is not None else {}
        after = read_fields(new)
    except ValueError:
        return ["(unreadable frontmatter)"]
    keys = (set(before) | set(after)) - QUIET_FIELDS
    return sorted(key for key in keys if before.get(key) != after.get(key))


def _over_allowance(scan: Scan, allowed: dict[str, Any]) -> list[str]:
    counts = allowed.get("counts", {}) if isinstance(allowed, dict) else {}
    return [
        f"{scan.counts[severity]} {severity}"
        for severity in BLOCKING
        if scan.counts.get(severity, 0) > int(counts.get(severity, 0))
    ]


@dataclass
class Upgrade:
    """What --upgrade did, for the CLI to print and turn into an exit code."""

    result: Result
    applied: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    undecided: list[str] = field(default_factory=list)
    network: str | None = None
    interrupted: str | None = None

    @property
    def changed(self) -> list[str]:
        return self.applied + self.added + self.removed

    @property
    def exit_code(self) -> int:
        if self.interrupted:
            return 130
        if self.network:
            return 3
        if self.refused or self.result.errors:
            return 1
        return 2 if self.undecided or self.result.preserved else 0


UPGRADE_CHOICES: Options = (("a", "apply"), ("s", "skip"), ("q", "quit"))
VIEW_CHOICE = ("v", "view the whole diff")
REMOVE_CHOICES: Options = (("r", "remove it"), ("k", "keep it for now"), ("q", "quit"))
DIRTY_PATHS = (".agents", ".claude/skills", "README.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md")
RECORD_FILES = (LOCK_NAME, SOURCES_NAME, OVERRIDES_NAME, PACKS_NAME)


# globals --upgrade: the transaction


def _now() -> str:
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _write_atomic(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.repo-template-tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _step(name: str) -> None:
    """A point in the transaction; tests make a process die here to check recovery."""


class Transaction:
    """One skill's swap and record writes. The journal is written first and holds the record
    files as they were, so an error, a signal or a kill at any point before `commit()` is
    undone by `rollback()`, now or by the next run's recover()."""

    def __init__(self, root: Path, stage_dir: Path, name: str, licenses: Sequence[Path] = ()):
        self.root, self.stage_dir, self.name = root, stage_dir, name
        self.folder = _home(root, name)
        self.target = root / self.folder / name
        for path in licenses:
            if path.exists():
                raise ValueError(f"{name}: {path} already exists; not overwriting it")
        saved = {}
        for relative in RECORD_FILES:
            path = root / relative
            saved[relative] = (
                base64.b64encode(path.read_bytes()).decode() if path.exists() else None
            )
        journal = {
            "name": name,
            "folder": self.folder,
            "had_skill": self.target.exists(),
            "records": saved,
            "licenses": [str(path.relative_to(root)) for path in licenses],
        }
        _write_atomic(stage_dir / "journal.json", json.dumps(journal).encode())
        _step("journaled")

    def swap(self, incoming: Path | None) -> None:
        if self.target.exists():
            os.rename(self.target, self.stage_dir / PREVIOUS)
            _step("moved-out")
        if incoming is not None:
            os.rename(incoming, self.target)
            _step("moved-in")

    def commit(self) -> None:
        journal = _journal(self.stage_dir)
        _write_atomic(
            self.stage_dir / "journal.json", json.dumps({**journal, "done": True}).encode()
        )
        _step("done")


def rollback(root: Path, stage_dir: Path) -> bool:
    """Undo a transaction that didn't commit: the record files as they were, the live folder
    put back, any license copies it added removed. Returns whether it undid anything."""
    journal = _journal(stage_dir)
    name = journal.get("name")
    if journal.get("done") or not isinstance(name, str) or not NAME.fullmatch(name):
        return False
    folder = (
        journal.get("folder") if journal.get("folder") in {SKILLS_DIR, PACKS_DIR} else SKILLS_DIR
    )
    target = root / str(folder) / name
    previous = stage_dir / PREVIOUS
    if previous.is_dir():  # the live folder was moved aside: whatever is at target is new
        if target.exists():
            os.rename(target, stage_dir / "rejected")
        os.rename(previous, target)
    elif not journal.get("had_skill") and target.exists():  # an addition got as far as live
        os.rename(target, stage_dir / "rejected")
    for relative in journal.get("licenses", []):
        path = root / relative
        if isinstance(relative, str) and path.parent == root / LICENSES_DIR:
            path.unlink(missing_ok=True)
    for relative, saved in (journal.get("records") or {}).items():
        if relative not in RECORD_FILES:
            continue
        path = root / relative
        if saved is None:
            path.unlink(missing_ok=True)
        else:
            data = base64.b64decode(saved)
            if not path.exists() or path.read_bytes() != data:
                _write_atomic(path, data)
    return True


def _journal(stage_dir: Path) -> dict[str, Any]:
    try:
        data = json.loads((stage_dir / "journal.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def recover(root: Path, result: Result) -> None:
    """Undo what an interrupted upgrade left half done, then drop its staging folders."""
    for stage_dir in sorted(root.glob(f"{STAGE_PREFIX}*")):
        journal = _journal(stage_dir)
        if rollback(root, stage_dir):
            where = f"{journal.get('folder', SKILLS_DIR)}/{journal['name']}"
            result.updated.append(f"{root / where} (rolled back an interrupted upgrade)")
        shutil.rmtree(stage_dir)


class _Records:
    """The lock, sources, overrides and packs, read fresh for each change and written as part
    of its transaction."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.reload()

    def reload(self) -> None:
        self.lock = _json(self.root, LOCK_NAME)
        self.sources = _json(self.root, SOURCES_NAME)
        self.overrides = (
            _json(self.root, OVERRIDES_NAME) if (self.root / OVERRIDES_NAME).is_file() else {}
        )
        self.packs = _json(self.root, PACKS_NAME) if (self.root / PACKS_NAME).is_file() else None
        self.packs_changed = False

    @property
    def skills(self) -> dict[str, Any]:
        skills: dict[str, Any] = self.lock.setdefault("skills", {})
        return skills

    def vendored(
        self,
        staged: Staged,
        allow_findings: str | None,
        over: list[str],
        source_record: dict[str, Any] | None,
        provenance: dict[str, Any] | None,
    ) -> None:
        self.reload()  # only this skill's changes go on top of what's on disk now
        target, now = staged.target, _now()
        previous = self.skills.get(target.name, {})
        self.skills[target.name] = {  # an existing entry keeps its place and unknown fields
            **previous,
            "source": target.source,
            "sourceType": "github",
            "sourceUrl": f"https://github.com/{target.source}.git",
            "skillPath": f"{target.folder}/SKILL.md",
            "skillFolderHash": staged.folder_sha,
            "installedAt": previous.get("installedAt", now),
            "updatedAt": now,
        }
        records = self.sources.setdefault("skills", {})
        record: dict[str, Any] = {"commit": staged.commit, "tree": staged.folder_sha}
        record.update(
            (k, v) for k, v in records.get(target.name, {}).items() if k not in {"commit", "tree"}
        )
        record.pop("ref", None)
        if target.ref != "HEAD":
            record["ref"] = target.ref
        if over:
            record["allowFindings"] = {"reason": allow_findings, "counts": staged.scan.counts}
        records[target.name] = record
        if source_record is not None:
            self.sources.setdefault("sources", {})[target.source] = source_record
        if provenance is not None and target.name in self.overrides:
            self.overrides[target.name].update(provenance)
        self.write()

    def removed(self, name: str) -> None:
        self.reload()
        for records in (
            self.skills,
            self.sources.get("skills", {}),
            self.sources.get("allowCommands", {}),
            self.overrides,
        ):
            records.pop(name, None)
        for pack in (self.packs or {}).values():
            if isinstance(pack, dict) and name in pack.get("skills", []):
                pack["skills"] = [skill for skill in pack["skills"] if skill != name]
                self.packs_changed = True
        self.write()

    def write(self) -> None:
        def encode(data: Any, newline: bool = True) -> bytes:
            return (
                json.dumps(data, indent=2, ensure_ascii=False) + ("\n" if newline else "")
            ).encode()

        _write_atomic(self.root / LOCK_NAME, encode(self.lock, newline=False))
        _step("lock-written")
        self.sources["skills"] = dict(sorted(self.sources.get("skills", {}).items()))
        self.sources["sources"] = dict(sorted(self.sources.get("sources", {}).items()))
        _write_atomic(self.root / SOURCES_NAME, encode(self.sources))
        _step("sources-written")
        if (self.root / OVERRIDES_NAME).is_file():
            _write_atomic(self.root / OVERRIDES_NAME, encode(self.overrides))
        if self.packs is not None and self.packs_changed:
            _write_atomic(self.root / PACKS_NAME, encode(self.packs))
        _step("records-written")


# globals --upgrade: licenses


@dataclass
class _License:
    """A new source's license, fetched and verified, waiting in the staging folder."""

    record: dict[str, Any]
    files: dict[Path, Path]  # final path under .agents/licenses -> staged copy


def _copyright(text: str) -> str:
    for match in COPYRIGHT.finditer(text):
        line = match.group(0).strip()
        if not NOT_A_HOLDER.search(line):
            return clean(line)
    return ""


def _fetch_license(
    github: GitHub, root: Path, source: str, upstream: Snapshot, stage_dir: Path
) -> _License:
    """A new source: the SPDX license GitHub detects, each license or notice file at its root,
    pinned, and the copyright line it states. Refuses when GitHub can't name the license."""
    detected = github.license(source)
    if detected in {None, "NOASSERTION", "NONE", "OTHER"}:
        raise ValueError(f"{source}: GitHub can't name its license; record it in {SOURCES_NAME}")
    entries = upstream.github.tree(source, upstream.root, recursive=False)[0]
    found = sorted(
        (
            entry
            for entry in entries
            if entry.mode in {"100644", "100755"} and LICENSE_FILE.fullmatch(entry.path)
        ),
        key=lambda entry: entry.path,
    )
    if not found:
        raise ValueError(f"{source}: no license file at its root; record it in {SOURCES_NAME}")
    pinned: dict[str, str] = {}
    files: dict[Path, Path] = {}
    stated = ""
    for entry in found:
        if not FOLDER.fullmatch(entry.path):
            raise ValueError(f"{source}: unusual license file name {clean(entry.path)!r}")
        data = github.blob(source, entry.sha)
        if blob_sha(data) != entry.sha:
            raise ValueError(f"{source}: {clean(entry.path)} doesn't match its blob SHA")
        staged = stage_dir / "licenses" / f"{source.replace('/', '_')}__{entry.path}.txt"
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(data)
        files[root / LICENSES_DIR / staged.name] = staged
        pinned[entry.path] = entry.sha
        stated = stated or _copyright(data.decode(errors="replace"))
    first = next(iter(pinned))
    record = {
        "license": detected,
        "copyright": stated or f"Not stated upstream (its {first} has no copyright line)",
        "licenseFiles": pinned,
        "discover": "none",
    }
    return _License(record, files)


# globals --upgrade: the changelog


CHANGELOG_NOTES = {
    "applied": "- Skills refreshed from upstream: ",
    "added": "- Skills added from upstream: ",
    "removed": "- Skills removed (gone upstream): ",
}


def note_in_changelog(path: Path, outcome: Upgrade) -> bool:
    """Add the upgrade's skills to `## Unreleased`, merging with what earlier upgrades noted
    there (a note wrapped over several lines included), so running it twice changes nothing.
    Keeps the file's line endings. Returns whether the file changed."""
    if path.is_file():
        with path.open(newline="") as handle:
            raw = handle.read()
    else:
        raw = "# Changelog\n"
    newline = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    ending = text[len(text.rstrip("\n")) :] or "\n"
    lines = text.rstrip("\n").split("\n")
    if "## Unreleased" not in lines:
        at = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
        lines[at:at] = ["## Unreleased", "", *([""] if at < len(lines) else [])]
        if at and lines[at - 1].strip():
            lines.insert(at, "")
    start = lines.index("## Unreleased") + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    section = lines[start:end]

    def bullet_end(index: int) -> int:
        """Past the bullet's own lines, and its indented paragraphs and nested lists."""
        index += 1
        while index < len(section):
            if section[index].startswith("  "):
                index += 1
                continue
            following = next((line for line in section[index:] if line.strip()), "")
            if not section[index].strip() and following.startswith("  "):
                index += 1
                continue
            break
        return index

    for kind, prefix in CHANGELOG_NOTES.items():
        names = set(getattr(outcome, kind))
        if not names:
            continue
        index = next((i for i, line in enumerate(section) if line.startswith(prefix)), None)
        if index is not None:
            stop = bullet_end(index)
            names |= set(re.findall(r"`([^`]+)`", " ".join(section[index:stop])))
            del section[index:stop]
        else:
            bullets = [i for i, line in enumerate(section) if line.startswith("- ")]
            index = bullet_end(bullets[-1]) if bullets else (1 if section else 0)
            while index > 0 and not section[index - 1].strip() and bullets:
                index -= 1  # right after the last bullet, before the blank line that ends it
        note = prefix + ", ".join(f"`{name}`" for name in sorted(names)) + "."
        wrapped = textwrap.wrap(
            note, width=100, subsequent_indent="  ", break_long_words=False, break_on_hyphens=False
        )
        section[index:index] = wrapped
    if not section or section[0].strip():
        section.insert(0, "")
    if end < len(lines) and section[-1].strip():
        section.append("")
    updated = "\n".join([*lines[:start], *section, *lines[end:]]) + ending
    if updated == text:
        return False
    _write_atomic(path, updated.replace("\n", newline).encode())
    return True


# globals --upgrade: the run


def _targets(
    specs: Sequence[str], lock: dict[str, Any], sources: dict[str, Any], snapshot: Snapshots
) -> list[Target]:
    parsed = [(spec, parse_spec(spec)) for spec in specs]
    named = [spec if found is None else found[1].rsplit("/", 1)[-1] for spec, found in parsed]
    if "skill-scanner" in named and len(named) > 1:
        raise ValueError("upgrade skill-scanner on its own: it vets every other upgrade")
    if not specs:
        return [
            Target(name, lock[name]["source"], _folder(lock[name]), _ref(sources, name), False)
            for name in sorted(lock)
            if name != "skill-scanner"
        ]
    targets: list[Target] = []
    for spec, found in parsed:
        if found is None:
            if spec not in lock:
                raise ValueError(
                    f"{spec!r} isn't vendored; to add it, name it as owner/repo@{spec}"
                )
            entry = lock[spec]
            targets.append(
                Target(spec, entry["source"], _folder(entry), _ref(sources, spec), False)
            )
            continue
        source, skill, ref = found
        try:
            upstream = snapshot(source, ref)
        except NotFound:
            raise ValueError(f"{spec!r}: {source}@{ref} isn't on GitHub") from None
        if "/" in skill:  # a path: the skill is named by its SKILL.md
            folder = skill
            text = upstream.text(f"{folder}/SKILL.md")
            if text is None:
                raise ValueError(f"{spec!r}: {source}@{ref} has no {folder}/SKILL.md")
            try:
                name = read_fields(text).get("name", "")
            except ValueError as exc:
                raise ValueError(f"{spec!r}: {exc}") from None
        else:
            folders = upstream.skill_folders()
            matches = (folders or {}).get(skill, [])
            if len(matches) != 1:
                where = f"several folders ({clean(', '.join(matches))})" if matches else "no folder"
                raise ValueError(
                    f"{spec!r}: {where} named {skill!r} with a SKILL.md; name its path instead"
                )
            folder, name = matches[0], skill
        if not FOLDER.fullmatch(folder):
            raise ValueError(f"{spec!r}: unusual folder path {clean(folder)!r}")
        if not NAME.fullmatch(name) or name in RESERVED:
            raise ValueError(f"{spec!r}: {clean(name)!r} isn't a usable skill name (a-z, 0-9, -)")
        if name in lock and lock[name]["source"] != source:
            raise ValueError(f"{name}: already vendored from {lock[name]['source']}")
        if name in sources.get("local", {}):
            raise ValueError(f"{name}: a local skill has that name")
        if name in sources.get("ignored", {}).get(source, {}):
            raise ValueError(f"{name}: listed under 'ignored' for {source} in {SOURCES_NAME}")
        if any(target.name == name for target in targets):
            raise ValueError(f"{name}: named twice")
        targets.append(Target(name, source, folder, ref, name not in lock))
    return targets


def _ignored(root: Path, name: str, paths: Sequence[str]) -> list[str]:
    """The staged paths this repository's Git would ignore (and so never track or hash)."""
    home = _home(root, name)
    listing = "\0".join(f"{home}/{name}/{path}" for path in paths).encode()
    done = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--no-index", "--stdin", "-z"],
        input=listing,
        capture_output=True,
        check=False,
    )
    prefix = f"{home}/{name}/"
    return [os.fsdecode(path)[len(prefix) :] for path in done.stdout.split(b"\0") if path]


def _prepare(
    root: Path,
    github: GitHub,
    upstream: Snapshot,
    target: Target,
    stage_dir: Path,
    scanner: Scanner,
    records: _Records,
) -> Staged:
    """Stage, verify, check and scan: everything that refuses a skill before anyone looks."""
    staged = stage(github, upstream, target, stage_dir / "incoming" / target.name)
    assert staged.path is not None
    text = (staged.path / "SKILL.md").read_text(errors="replace")
    named = read_fields(text).get("name")
    if named != target.name:
        raise ValueError(f"{target.name}: its SKILL.md names it {clean(str(named))!r}")
    if target.name not in records.sources.get("allowCommands", {}):
        loads = []
        for markdown in sorted(staged.path.rglob("*.md")):
            content = markdown.read_text(errors="replace")
            loads += runs_on_load(content) if markdown.name == "SKILL.md" else []
            loads += [] if markdown.name == "SKILL.md" else load_commands(content)
        if loads:
            raise ValueError(
                f"{target.name}: runs commands when it loads ({clean(loads[0])[:60]}); review "
                f"it, then allow it under 'allowCommands' in {SOURCES_NAME}"
            )
    ignored = _ignored(root, target.name, sorted(_files(staged.path)))
    if ignored:
        raise ValueError(
            f"{target.name}: this repository's .gitignore would hide "
            f"{clean(', '.join(ignored[:5]))}, so they couldn't be tracked or checked"
        )
    source_license = records.sources.get("sources", {}).get(target.source, {})
    spdx = source_license.get("license", "") if isinstance(source_license, dict) else ""
    own = own_license(staged.path, text, str(spdx))
    if own and not records.sources.get("skills", {}).get(target.name, {}).get("license"):
        raise ValueError(
            f"{target.name}: carries its own license ({clean(', '.join(own))}); record it as "
            f"'license' and 'copyright' under 'skills' in {SOURCES_NAME}, then upgrade it"
        )
    if not target.adding or target.source in records.sources.get("sources", {}):
        changes = _license_changes(records.sources, target.source, upstream)
        if changes:
            raise ValueError(
                f"{target.name}: {target.source}'s {'; '.join(changes)}; review the license "
                f"and pin the new text in {SOURCES_NAME} first"
            )
    staged.scan = scanner.scan(staged.path)
    if staged.scan.error:
        raise ValueError(f"{target.name}: {staged.scan.summary()}; nothing applied")
    return staged


def _review(prompt: Prompt, header: str, diff: Diff, notes: list[str], question: str) -> str:
    prompt.say(visible(header))
    for line in notes:
        prompt.say(visible(f"  ! {line}"))
    for line in diff.summary:
        prompt.say(visible(f"  {line}"))
    truncated = len(diff.lines) > DIFF_LINES
    prompt.diff(diff.lines[:DIFF_LINES])
    if truncated:
        prompt.say(f"  … {len(diff.lines) - DIFF_LINES} more diff lines; [v] shows them")
    choices: Options = (*UPGRADE_CHOICES, VIEW_CHOICE) if truncated else UPGRADE_CHOICES
    choice = prompt.choose(question, choices)
    if choice == "v":
        prompt.diff(diff.lines)
        choice = prompt.choose(question, UPGRADE_CHOICES)
    return choice


@contextmanager
def _exclusive(root: Path) -> Iterator[None]:
    """One --upgrade at a time per repository: a lock in the Git directory, released when the
    process ends, however it ends."""
    try:
        import fcntl
    except ImportError:  # no flock (Windows): run unguarded
        yield
        return
    git_dir = Path(_git(root, "rev-parse", "--absolute-git-dir").decode().strip())
    with (git_dir / "repo-template-upgrade.lock").open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another `globals --upgrade` is running in this repository") from None
        yield


@contextmanager
def _signals_raise() -> Iterator[None]:
    """SIGTERM and SIGHUP raise, so rollbacks and the final linking still run."""

    def interrupt(number: int, frame: FrameType | None) -> None:
        raise _Interrupted(signal.Signals(number).name)

    caught = [sig for sig in (signal.SIGTERM, getattr(signal, "SIGHUP", None)) if sig is not None]
    previous = {}
    try:
        for sig in caught:
            previous[sig] = signal.signal(sig, interrupt)
    except ValueError:  # not the main thread: leave signals alone
        previous = {}
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def upgrade(
    root: Path,
    specs: Sequence[str],
    *,
    github: GitHub,
    scanner: Scanner,
    prompt: Prompt | None,
    allow_findings: str | None = None,
    home: Path | None = None,
) -> Upgrade:
    """Vendor the named skills (or every changed one): stage, verify, scan, show, ask, swap.
    `prompt` is None for --no-input. Never commits."""
    if allow_findings is not None and (prompt is None or not allow_findings.strip()):
        raise ValueError("--allow-findings needs a reason, and a terminal to confirm each skill")
    with _exclusive(root), _signals_raise():
        outcome = Upgrade(Result(root))
        recover(root, outcome.result)
        dirty = _git(
            root, "status", "--porcelain", "--untracked-files=all", "--", *DIRTY_PATHS
        ).decode()
        if dirty.strip():
            raise ValueError(
                "commit or stash the changes to .agents, .claude/skills, README.md, "
                "CHANGELOG.md and THIRD_PARTY_NOTICES.md first, so the upgrade can be reviewed "
                "on its own:\n" + clean(dirty.strip())
            )
        try:
            _upgrade(root, specs, outcome, github, scanner, prompt, allow_findings)
        except (KeyboardInterrupt, _Interrupted) as exc:
            outcome.interrupted = str(exc) or type(exc).__name__
        finally:
            if outcome.changed:
                _finish(root, outcome, home)
        return outcome


def _upgrade(
    root: Path,
    specs: Sequence[str],
    outcome: Upgrade,
    github: GitHub,
    scanner: Scanner,
    prompt: Prompt | None,
    allow_findings: str | None,
) -> None:
    records = _Records(root)
    snapshot = _snapshots(github)
    try:
        targets = _targets(specs, records.skills, records.sources, snapshot)
    except NotFound as exc:
        raise ValueError(str(exc)) from None
    except NetworkError as exc:
        outcome.network = str(exc)
        return
    if prompt is None and any(t.name == "skill-scanner" for t in targets):
        raise ValueError("upgrade skill-scanner in a terminal, without --no-input")
    named = {target.name for target in targets} if specs else set()
    for position, target in enumerate(targets):
        try:
            records.reload()  # anything edited by hand meanwhile is kept
            _upgrade_one(root, target, outcome, records, github, snapshot, scanner, prompt,
                         allow_findings, named)  # fmt: skip
        except _Quit:
            outcome.undecided += [t.name for t in targets[position:]]
            break
        except NotFound as exc:
            outcome.refused.append(f"{target.name}: not upstream any more: {exc}")
        except NetworkError as exc:
            outcome.network = str(exc)
            outcome.undecided += [t.name for t in targets[position:]]
            break
        except (ValueError, OSError, KeyError, TypeError) as exc:
            message = clean(str(exc))
            prefix = f"{target.name}: "
            outcome.refused.append(message if message.startswith(prefix) else prefix + message)
        finally:
            for leftover in root.glob(f"{STAGE_PREFIX}*"):
                rollback(root, leftover)
                shutil.rmtree(leftover, ignore_errors=True)


class _Quit(Exception):
    pass


def _ask_or_leave(
    target: Target, outcome: Upgrade, prompt: Prompt | None, named: set[str], message: str
) -> bool:
    """For a change shown without a diff: True to go ahead. --no-input goes ahead only for a
    named skill."""
    if prompt is None:
        if target.name in named:
            return True
        outcome.undecided.append(f"{target.name}: {message}; not named, so left as it is")
        return False
    prompt.say(visible(f"{target.name}: {message}."))
    choice = prompt.choose("record it", UPGRADE_CHOICES)
    if choice == "q":
        raise _Quit
    if choice == "s":
        outcome.undecided.append(f"{target.name}: skipped")
        return False
    return True


def _upgrade_one(
    root: Path,
    target: Target,
    outcome: Upgrade,
    records: _Records,
    github: GitHub,
    snapshot: Snapshots,
    scanner: Scanner,
    prompt: Prompt | None,
    allow_findings: str | None,
    named: set[str],
) -> None:
    upstream = snapshot(target.source, target.ref)
    sha = upstream.folder(target.folder)
    entry = records.skills.get(target.name, {})
    if sha is None and not target.adding:
        moved = upstream.moved(target.name, target.folder)
        if moved is None:
            outcome.undecided.append(
                f"{target.name}: not at {target.folder} upstream, and the tree is too large to "
                f"tell whether it moved; not removing it"
            )
            return
        if len(moved) > 1:
            outcome.undecided.append(
                f"{target.name}: moved to several folders ({clean(', '.join(moved))}); name one "
                f"as {target.source}@<folder>"
            )
            return
        if not moved:
            _remove(root, target, outcome, records, prompt)
            return
        if not FOLDER.fullmatch(moved[0]):
            raise ValueError(f"{target.name}: moved to an unusual path {clean(moved[0])!r}")
        target = replace(target, folder=moved[0])
        sha = upstream.folder(target.folder)
    record = records.sources.get("skills", {}).get(target.name, {})
    same_place = target.folder == _folder(entry) and target.ref == _ref(
        records.sources, target.name
    )
    if not target.adding and sha is not None and sha == entry.get("skillFolderHash"):
        if same_place:
            outcome.result.unchanged.append(target.name)
            return
        message = f"the same files, now at {target.folder}@{target.ref} upstream"
        if not _ask_or_leave(target, outcome, prompt, named, message):
            return
        _apply(root, Staged(target, upstream.commit, sha, None), None, None, records, None, [])
        outcome.applied.append(target.name)
        return
    stage_dir = Path(tempfile.mkdtemp(prefix=STAGE_PREFIX, dir=root))
    staged = _prepare(root, github, upstream, target, stage_dir, scanner, records)
    assert staged.path is not None
    over = _over_allowance(staged.scan, record.get("allowFindings", {}))
    current = root / _home(root, target.name) / target.name
    new_text = read_skill(staged.path / "SKILL.md")
    replaced: dict[str, str] = {}
    notes: list[str] = []
    override_entry = records.overrides.get(target.name)
    old_text = read_skill(current / "SKILL.md") if (current / "SKILL.md").is_file() else None
    if isinstance(override_entry, dict) and old_text is not None:
        with suppress(ValueError):  # a broken override shows as a plain diff
            old_text = upstream_skill_md(old_text, override_entry, None)
            replaced["SKILL.md"] = old_text
        for key in _stale_override(override_entry, new_text, override_entry.get("frontmatter", {})):
            notes.append(f"upstream changed its {key!r}, which an override replaces; review it")
    live = _tracked(root, target.name) if current.is_dir() else None
    diff = folder_diff(current, staged.path, target.name, replaced, live)
    read = staged.scan.read
    unscanned = [p for p in diff.changed if not (p in read if read is not None else scanned(p))]
    if unscanned:
        notes.append("skill-scanner doesn't read these; review them: " + ", ".join(unscanned))
    if diff.binary:
        notes.append("binary, not shown; review them: " + ", ".join(diff.binary))
    if diff.escaped:
        notes.append("control characters, shown escaped, in: " + ", ".join(diff.escaped))
    if diff.new_urls:
        notes.append("new URLs: " + ", ".join(diff.new_urls[:8]))
    if staged.scan.untrusted_urls:
        notes.append("untrusted URLs: " + ", ".join(staged.scan.untrusted_urls[:8]))
    permissions = _frontmatter_changes(old_text, new_text)
    if permissions:
        notes.append("frontmatter that decides what it may do changed: " + ", ".join(permissions))
    if target.folder != _folder(entry) and not target.adding:
        notes.append(f"moved upstream from {_folder(entry)} to {target.folder}")
    if prompt is None:
        if target.name not in named:
            why = "not named"
        elif staged.scan.total:
            why = staged.scan.summary()
        else:
            why = notes[0] if notes else ""
        if why:
            outcome.undecided.append(f"{target.name}: {why}; upgrade it in a terminal")
            return
    else:
        was = str(record.get("commit", ""))[:12] or "not vendored"
        header = (
            f"{target.name}: {target.source}@{target.ref} {was} → {staged.commit[:12]} "
            f"({staged.scan.summary()})"
        )
        if over and allow_findings is None:
            raise ValueError(
                f"{target.name}: {', '.join(over)} findings beyond its reviewed allowance; read "
                f"them (uv run .agents/skills/skill-scanner/scripts/scan_skill.py <folder>), "
                f"then pass --allow-findings REASON to apply it"
            )
        question = f"apply despite {', '.join(over)}" if over else "apply"
        choice = _review(prompt, header, diff, notes, question)
        if choice == "q":
            raise _Quit
        if choice == "s":
            outcome.undecided.append(f"{target.name}: skipped")
            return
    provenance = None
    if isinstance(override_entry, dict):  # the folder never goes live without its override
        spdx = records.sources.get("sources", {}).get(target.source, {}).get("license", "?")
        url = upstream_url(target.source, staged.commit, target.folder)
        upstream_text, overridden = override(
            new_text,
            override_entry.get("frontmatter", {}),
            override_entry,
            True,
            f"Original: {url} ({record.get('license') or spdx}).",
        )
        (staged.path / "SKILL.md").write_bytes(overridden.encode())
        provenance = {
            "upstream": blob_sha(upstream_text.encode()),
            "base": {
                key: field_lines(upstream_text, key)
                for key in override_entry.get("frontmatter", {})
            },
        }
    license_ = None
    if target.adding and target.source not in records.sources.get("sources", {}):
        license_ = _fetch_license(github, root, target.source, upstream, stage_dir)
    _apply(root, staged, stage_dir, allow_findings, records, license_, over, provenance)
    (outcome.added if target.adding else outcome.applied).append(target.name)
    try:
        moved = [str(path.relative_to(root)) for path in (license_.files if license_ else {})]
        _intend_to_add(root, [f"{_home(root, target.name)}/{target.name}", *moved])
    except ValueError as exc:
        outcome.result.errors.append(f"{target.name}: applied, but `git add -N` failed: {exc}")


def _apply(
    root: Path,
    staged: Staged,
    stage_dir: Path | None,
    allow_findings: str | None,
    records: _Records,
    license_: _License | None,
    over: list[str],
    provenance: dict[str, Any] | None = None,
) -> None:
    """Swap the staged folder in (if any) and write its records, as one transaction."""
    stage_dir = stage_dir or Path(tempfile.mkdtemp(prefix=STAGE_PREFIX, dir=root))
    licenses = list(license_.files) if license_ else []
    transaction = Transaction(root, stage_dir, staged.target.name, licenses)
    try:
        if staged.path is not None:
            transaction.swap(staged.path)
        for final, copy in (license_.files if license_ else {}).items():
            os.rename(copy, final)
        _step("licenses-moved")
        records.vendored(
            staged, allow_findings, over, license_.record if license_ else None, provenance
        )
        transaction.commit()
    except BaseException:
        rollback(root, stage_dir)
        records.reload()
        raise


def _remove(
    root: Path, target: Target, outcome: Upgrade, records: _Records, prompt: Prompt | None
) -> None:
    if prompt is None:
        outcome.undecided.append(f"{target.name}: gone upstream; decide in a terminal")
        return
    prompt.say(visible(f"{target.name}: no longer anywhere in {target.source}@{target.ref}."))
    choice = prompt.choose("remove it", REMOVE_CHOICES)
    if choice == "q":
        raise _Quit
    if choice == "k":
        outcome.undecided.append(f"{target.name}: kept, though gone upstream")
        return
    stage_dir = Path(tempfile.mkdtemp(prefix=STAGE_PREFIX, dir=root))
    transaction = Transaction(root, stage_dir, target.name)
    try:
        transaction.swap(None)
        records.removed(target.name)
        transaction.commit()
    except BaseException:
        rollback(root, stage_dir)
        records.reload()
        raise
    outcome.removed.append(target.name)


def _finish(root: Path, outcome: Upgrade, home: Path | None) -> None:
    """Link, regenerate and note what the upgrade changed, even when a later skill failed."""
    from repo_template.standards import sync_globals  # standards imports catalog, not this

    synced = sync_globals(root, home=home)
    for name in ("created", "updated", "removed", "preserved", "errors"):
        getattr(outcome.result, name).extend(getattr(synced, name))
    if note_in_changelog(root / "CHANGELOG.md", outcome):
        outcome.result.updated.append(f"{root / 'CHANGELOG.md'} (## Unreleased)")


def _intend_to_add(root: Path, paths: Sequence[str]) -> None:
    """Record new files in the index without staging any content, since integrity hashes what
    Git tracks. Nothing else is staged: changes and deletions stay unstaged."""
    listing = _git(root, "ls-files", "-o", "--exclude-standard", "-z", "--", *paths)
    new = [os.fsdecode(path) for path in listing.split(b"\0") if path]
    if new:
        _git(root, "add", "--intent-to-add", "--", *new)
