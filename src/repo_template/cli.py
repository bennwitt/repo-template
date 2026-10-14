from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from repo_template.mcp import MCP_SERVERS_NAME, load_mcp_servers
from repo_template.model import Result
from repo_template.pins import HttpRegistry, check_pins
from repo_template.repository import SUBPROCESS, create_repository, update_repository
from repo_template.resolve import TerminalPrompt, resolve_conflicts
from repo_template.scaffold import manifest_version, normalize_project_name
from repo_template.standards import find_standards_root, sync_globals
from repo_template.upstream import (
    GhApi,
    HeadScanner,
    NetworkError,
    clean,
    upgrade,
    upstream_report,
)


def _python_version(value: str) -> str:
    if not re.fullmatch(r"3\.\d+", value):
        raise argparse.ArgumentTypeError("use a major.minor version such as 3.12")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-template",
        description="Create, update, and validate standardized repositories.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("new", help="create a new standardized repository")
    create.add_argument("name", help="repository name")
    create.add_argument(
        "--parent",
        type=Path,
        default=Path.cwd(),
        help="parent directory (default: current directory)",
    )
    create.add_argument("--description", help="one-line project description")
    create.add_argument(
        "--python", type=_python_version, default="3.12", help="Python version (default: 3.12)"
    )
    create.add_argument("--no-git", action="store_true", help="do not initialize Git")
    create.add_argument("--no-lock", action="store_true", help="do not create uv.lock")
    create.add_argument(
        "--pack",
        action="append",
        default=[],
        metavar="NAME",
        help="link a skill pack from ~/.agents/skill-packs.json into the repository",
    )

    update = subparsers.add_parser("update", help="add missing standards safely")
    update.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=Path.cwd(),
        help="the repository (default: the current directory)",
    )
    update.add_argument(
        "--no-hooks", action="store_true", help="do not configure the repository hook path"
    )
    update.add_argument("--no-lock", action="store_true", help="do not create or refresh uv.lock")
    update.add_argument(
        "--pack",
        action="append",
        default=[],
        metavar="NAME",
        help="add a skill pack to the repository's manifest and link it",
    )
    update.add_argument(
        "--no-input",
        action="store_true",
        help="list files that differ from the baseline instead of asking about each one",
    )
    update.add_argument(
        "--packs-only",
        action="store_true",
        help="adopt a repository for its skill packs (and their MCP servers) alone: no baseline "
        "files, hook path or lockfile; recorded, so later runs need no flag",
    )
    update.add_argument(
        "--personal",
        action="store_true",
        help="adopt a repository you don't manage for your own skill packs: nothing anyone else "
        "sees changes (the record is in .git, the links in .git/info/exclude, the MCP servers "
        "in Claude Code's local scope); recorded, so later runs need no flag",
    )

    check = subparsers.add_parser(
        "check", help="report what update would change, without writing anything"
    )
    check.add_argument(
        "paths",
        type=Path,
        nargs="*",
        metavar="path",
        help="repositories to check (default: the current directory); with several, one "
        "summary line each",
    )
    check.add_argument("--no-hooks", action="store_true", help="ignore the Git hook path")
    check.add_argument("--no-lock", action="store_true", help="ignore uv.lock")
    check.add_argument(
        "--pack",
        action="append",
        default=[],
        metavar="NAME",
        help="plan as if this skill pack were added (as update --pack would)",
    )
    check.add_argument(
        "--packs-only",
        action="store_true",
        help="plan a packs-only adoption (as update --packs-only would)",
    )
    check.add_argument(
        "--personal",
        action="store_true",
        help="plan a personal adoption (as update --personal would)",
    )

    globals_parser = subparsers.add_parser(
        "globals", help="connect global Codex and Claude configuration to this standards repo"
    )
    globals_parser.add_argument(
        "--standards-root",
        type=Path,
        help="the standards repository (default: $AI_DEV_STANDARDS, else the checkout this CLI "
        "is installed from)",
    )
    mode = globals_parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report changes without applying them")
    mode.add_argument(
        "--upstream",
        action="store_true",
        help="compare the vendored skills, license texts and MCP pins with upstream (GitHub, npm "
        "and PyPI; read-only)",
    )
    mode.add_argument(
        "--upgrade",
        action="store_true",
        help="vendor skills from upstream, each verified, scanned and shown before it goes live: "
        "the SKILLs named, or every changed one",
    )
    globals_parser.add_argument(
        "skills",
        nargs="*",
        metavar="SKILL",
        help="with --upgrade: a vendored skill, or owner/repo@skill-or-path[#ref] to add one",
    )
    globals_parser.add_argument(
        "--no-input",
        action="store_true",
        help="with --upgrade: apply only the named skills, and only with a clean scan",
    )
    globals_parser.add_argument(
        "--allow-findings",
        metavar="REASON",
        help="with --upgrade: apply despite critical or high findings beyond a skill's reviewed "
        "allowance, recording REASON (asks for each skill)",
    )
    return parser


def _print_result(result: Result, *, check: bool = False, preserved: bool = True) -> None:
    verb = "Would create" if check else "Created"
    if result.created:
        print(f"{verb} ({len(result.created)}):")
        for path in result.created:
            print(f"  + {path}")
    verb = "Would update" if check else "Updated"
    if result.updated:
        print(f"{verb} ({len(result.updated)}):")
        for path in result.updated:
            print(f"  ~ {path}")
    verb = "Would remove" if check else "Removed"
    if result.removed:
        print(f"{verb} ({len(result.removed)}):")
        for path in result.removed:
            print(f"  - {path}")
    if result.preserved and preserved:
        print(f"Preserved for manual review ({len(result.preserved)}):")
        for path in result.preserved:
            print(f"  ! {path}")
    if result.notes:
        print(f"Notes ({len(result.notes)}):")
        for note in result.notes:
            print(f"  · {note}")
    if result.errors:
        print(f"Errors ({len(result.errors)}):", file=sys.stderr)
        for error in result.errors:
            print(f"  x {error}", file=sys.stderr)
    if not result.needs_attention:
        print("Standards are current.")


def _new(args: argparse.Namespace) -> int:
    project = normalize_project_name(args.name)
    target = args.parent.expanduser().resolve() / project
    description = args.description or f"{project} project."
    result = create_repository(
        target,
        name=project,
        description=description,
        python_version=args.python,
        git=not args.no_git,
        lock=not args.no_lock,
        packs=args.pack,
    )
    _print_result(result)
    print(f"\nRepository: {target}")
    return 1 if result.errors else 0


def _interactive(args: argparse.Namespace) -> bool:
    return not args.no_input and sys.stdin.isatty() and sys.stdout.isatty()


def _update(args: argparse.Namespace) -> int:
    hooks, lock = not args.no_hooks, not args.no_lock
    result = update_repository(
        args.path,
        hooks=hooks,
        lock=lock,
        packs=args.pack,
        packs_only=args.packs_only,
        personal=args.personal,
    )
    # Only baseline files conflict, so packs-only and personal runs never reach the second pass
    # below (which relies on the recorded profile, not the flags).
    if result.conflicts and _interactive(args):
        _print_result(result, preserved=False)
        print()
        try:
            outcomes = resolve_conflicts(
                result.root, result.conflicts, TerminalPrompt(), SUBPROCESS
            )
        except KeyboardInterrupt:
            print("\nStopped. Decisions made so far are applied; run update again to continue.")
            return 1 if result.errors else 2
        print("\nDecisions:")
        for path, outcome in outcomes:
            print(f"  {path}: {outcome}")
        print()
        first = result
        result = update_repository(args.path, hooks=hooks, lock=lock)
        # A failure in the first pass (say `uv lock`) isn't repeated by the second, which sees
        # pyproject.toml unchanged; it still decides the exit code.
        result.errors[:0] = [error for error in first.errors if error not in result.errors]
    _print_result(result)
    if result.conflicts and not _interactive(args):
        print("Run `repo-template update` in a terminal to compare and decide each file.")
    return _exit_code(result)


def _exit_code(result: Result) -> int:
    """Errors win over preserved files: fix what failed first, then decide what was kept."""
    return 1 if result.errors else (2 if result.preserved else 0)


def _check(args: argparse.Namespace) -> int:
    paths = args.paths or [Path.cwd()]
    if len(paths) == 1:
        result = update_repository(
            paths[0],
            check=True,
            hooks=not args.no_hooks,
            lock=not args.no_lock,
            packs=args.pack,
            packs_only=args.packs_only,
            personal=args.personal,
        )
        _print_result(result, check=True)
        return 1 if result.needs_attention else 0
    drifted = 0
    for path in paths:
        try:
            result = update_repository(
                path,
                check=True,
                hooks=not args.no_hooks,
                lock=not args.no_lock,
                packs=args.pack,
                packs_only=args.packs_only,
                personal=args.personal,
            )
        except (OSError, ValueError) as exc:
            print(f"{path}: error")
            print(f"repo-template: error: {path}: {exc}", file=sys.stderr)
            drifted += 1
            continue
        version = manifest_version(result.root) or "no manifest"
        print(f"{path}: {_summary(result)} ({version})")
        for error in result.errors:
            print(f"repo-template: error: {path}: {error}", file=sys.stderr)
        drifted += result.needs_attention
    return 1 if drifted else 0


def _summary(result: Result) -> str:
    """One line for a repository's check: what update would do there."""
    if not result.needs_attention:
        return "current"
    counts = [
        (len(result.created), "to create"),
        (len(result.updated), "to update"),
        (len(result.removed), "to remove"),
        (len(result.preserved), "for review"),
        (len(result.errors), "errors"),
    ]
    return ", ".join(f"{count} {label}" for count, label in counts if count)


def _upstream(root: Path) -> int:
    try:
        report = upstream_report(root, GhApi())
        if (root / ".agents" / MCP_SERVERS_NAME).is_file():
            servers = load_mcp_servers(root / ".agents")
            check_pins(servers, HttpRegistry(), datetime.now(UTC), report)
    except NetworkError as exc:
        print(f"repo-template: error: {exc}", file=sys.stderr)
        return 3
    for title, lines in (
        ("Changed upstream", report.changed),
        ("Needs review", report.review),
        ("New upstream, not vendored", report.new),
        ("Notes", report.notes),
    ):
        if lines:
            print(f"{title} ({len(lines)}):")
            for line in lines:
                print(f"  {clean(line)}")
    if report.exit_code == 0:
        pins = f" and {len(report.pins)} MCP pins" if report.pins else ""
        print(f"All {len(report.current)} vendored skills{pins} are current.")
    elif len(report.changed) > report.pin_changes:
        print("Run `repo-template globals --upgrade` to review and apply the skills.")
    return report.exit_code


def _upgrade(root: Path, args: argparse.Namespace) -> int:
    if not args.no_input and not sys.stdin.isatty():
        print(
            "repo-template: error: --upgrade asks about each skill; run it in a terminal, or "
            "pass --no-input",
            file=sys.stderr,
        )
        return 1
    with HeadScanner(root) as scanner:
        outcome = upgrade(
            root,
            args.skills,
            github=GhApi(),
            scanner=scanner,
            prompt=None if args.no_input else TerminalPrompt(),
            allow_findings=args.allow_findings,
        )
    if outcome.result.needs_attention:
        _print_result(outcome.result)
    for title, names in (
        ("Refreshed", outcome.applied),
        ("Added", outcome.added),
        ("Removed", outcome.removed),
        ("Left as they are", outcome.undecided),
    ):
        if names:
            print(f"{title} ({len(names)}):")
            for name in names:
                print(f"  {clean(name)}")
    for refusal in outcome.refused:
        print(f"repo-template: refused: {clean(refusal)}", file=sys.stderr)
    if outcome.network:
        print(f"repo-template: error: {clean(outcome.network)}", file=sys.stderr)
    if outcome.changed:
        if outcome.result.errors:
            print("Fix the errors above before committing.")
        print("Review with `git status` and `git diff`, then commit:")
        print("  git add .agents README.md THIRD_PARTY_NOTICES.md CHANGELOG.md .claude/skills")
        print(f"  git commit -m 'Upgrade skills: {', '.join(outcome.changed)}'")
    return outcome.exit_code


def _globals(args: argparse.Namespace) -> int:
    root = find_standards_root(args.standards_root)
    if args.upstream:
        return _upstream(root)
    if args.upgrade:
        return _upgrade(root, args)
    result = sync_globals(root, check=args.check)
    _print_result(result, check=args.check)
    if args.check:
        return 1 if result.needs_attention else 0
    return _exit_code(result)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args, extra = parser.parse_known_args(argv)
    if (
        extra
        and args.command == "globals"
        and args.upgrade
        and not any(arg.startswith("-") for arg in extra)
    ):
        args.skills += extra  # skill names on both sides of an option
    elif extra:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    upgrade_only = args.command == "globals" and (
        args.no_input or args.allow_findings is not None or args.skills
    )
    if upgrade_only and not args.upgrade:
        parser.error("SKILL, --no-input and --allow-findings work only with --upgrade")
    try:
        if args.command == "new":
            return _new(args)
        if args.command == "update":
            return _update(args)
        if args.command == "check":
            return _check(args)
        if args.command == "globals":
            return _globals(args)
    except (OSError, ValueError) as exc:
        # Exit 2 means "preserved for manual review" (and argparse usage errors), so a runtime
        # failure (unknown pack, unreadable manifest, non-empty target) exits 1.
        print(f"repo-template: error: {exc}", file=sys.stderr)
        return 1
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
