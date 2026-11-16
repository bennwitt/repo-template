"""`repo-template-mcp NAME`: run one of the standards repository's own MCP servers.

Each lives in servers/NAME as a uv project with its lockfile, and runs from the standards
checkout ~/.agents links to, with exactly its locked dependencies. A committed .mcp.json then
names this command and the server, never a path on one machine. This is a launcher for MCP
clients, not part of the public CLI.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from repo_template.mcp import SERVER_NAME, SERVERS_DIR


def server_dir(agents: Path, name: str) -> Path:
    """Where server NAME lives: servers/NAME beside the catalog's .agents folder."""
    return agents.resolve().parent / SERVERS_DIR / name


def command(uv: str, folder: Path, name: str) -> list[str]:
    """uv runs the server's own script in its locked environment; --quiet keeps uv's notes
    off the protocol (they go to stderr anyway), and the caller's folder stays the cwd."""
    return [uv, "run", "--project", str(folder), "--locked", "--no-dev", "--quiet", name]


def main(argv: Sequence[str] | None = None, agents: Path | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or not SERVER_NAME.fullmatch(args[0]):
        print("usage: repo-template-mcp SERVER (a folder in the standards repository's "
              f"{SERVERS_DIR}/)", file=sys.stderr)  # fmt: skip
        return 2
    name = args[0]
    folder = server_dir(agents or Path.home() / ".agents", name)
    if not (folder / "pyproject.toml").is_file() or not (folder / "uv.lock").is_file():
        print(
            f"repo-template-mcp: no server {name!r} at {folder}; ~/.agents should link into "
            f"the standards checkout (setup-machine.sh, then repo-template globals)",
            file=sys.stderr,
        )
        return 1
    uv = shutil.which("uv")
    if uv is None:
        print("repo-template-mcp: uv isn't on PATH", file=sys.stderr)
        return 1
    os.execv(uv, command(uv, folder, name))
    return 0  # not reached: execv replaces this process


if __name__ == "__main__":
    raise SystemExit(main())
