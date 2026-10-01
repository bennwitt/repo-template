from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from repo_template.model import Result
from repo_template.repository import SUBPROCESS, create_repository, update_repository
from repo_template.resolve import TerminalPrompt, resolve_conflicts
from repo_template.scaffold import normalize_project_name
from repo_template.standards import find_standards_root, sync_globals


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
    create.add_argument("--python", type=_python_version, default="3.12")
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
    update.add_argument("path", type=Path, nargs="?", default=Path.cwd())
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

    check = subparsers.add_parser(
        "check", help="report what update would change, without writing anything"
    )
    check.add_argument("path", type=Path, nargs="?", default=Path.cwd())
    check.add_argument("--no-hooks", action="store_true", help="ignore the Git hook path")
    check.add_argument("--no-lock", action="store_true", help="ignore uv.lock")

    globals_parser = subparsers.add_parser(
        "globals", help="connect global Codex and Claude configuration to this standards repo"
    )
    globals_parser.add_argument("--standards-root", type=Path)
    globals_parser.add_argument(
        "--check", action="store_true", help="report changes without applying them"
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
    result = update_repository(args.path, hooks=hooks, lock=lock, packs=args.pack)
    if result.conflicts and _interactive(args):
        _print_result(result, preserved=False)
        print()
        try:
            outcomes = resolve_conflicts(
                result.root, result.conflicts, TerminalPrompt(), SUBPROCESS
            )
        except KeyboardInterrupt:
            print("\nStopped. Decisions made so far are applied; run update again to continue.")
            return 2
        print("\nDecisions:")
        for path, outcome in outcomes:
            print(f"  {path}: {outcome}")
        print()
        result = update_repository(args.path, hooks=hooks, lock=lock)
    _print_result(result)
    if result.conflicts and not _interactive(args):
        print("Run `repo-template update` in a terminal to compare and decide each file.")
    return 2 if result.preserved else (1 if result.errors else 0)


def _check(args: argparse.Namespace) -> int:
    result = update_repository(
        args.path, check=True, hooks=not args.no_hooks, lock=not args.no_lock
    )
    _print_result(result, check=True)
    return 1 if result.needs_attention else 0


def _globals(args: argparse.Namespace) -> int:
    root = find_standards_root(args.standards_root)
    result = sync_globals(root, check=args.check)
    _print_result(result, check=args.check)
    return 1 if args.check and result.needs_attention else 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
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
        parser.error(str(exc))
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
