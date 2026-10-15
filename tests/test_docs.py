"""The documents agree with what they describe: the tool pins, the flags of the CLI and of
setup-machine.sh, the global ignore entries, and every link and anchor inside this repository."""

from __future__ import annotations

import argparse
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from repo_template.cli import _parser
from repo_template.standards import GITIGNORE_CONTENT
from repo_template.tools import load_machine_tools

ROOT = Path(__file__).resolve().parents[1]
GUIDE = "HOW_TO_UPDATE_MACHINE_AND_ITS_REPOS.md"
DOCS = [
    "README.md",
    GUIDE,
    "AGENTS.md",
    "GLOSSARY.md",
    "CHANGELOG.md",
    ".agents/skills/repo-template/SKILL.md",
]
CURRENT = [doc for doc in DOCS if doc != "CHANGELOG.md"]  # the changelog keeps old flags
SCRIPT = ROOT / "setup-machine.sh"
FLAG = re.compile(r"(?<![\w-])--[a-z][a-z-]*")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
# Flags the docs name for other tools: npm and uv, and the MCP server args the catalog refuses.
OTHER_TOOLS = {"--before", "--locked", "--flag", "--index", "--namespace", "--package"} | {
    "--read-only",
    "--subscription",
    "--transport",
    "--with",
    "--dangerously-",
    "--insecure-",
}


def _text(doc: str) -> str:
    return (ROOT / doc).read_text()


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    fenced = False
    for line in path.read_text().splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and (heading := re.match(r"#{1,6} (.+)", line)):
            slug, n = _slug(heading.group(1)), 1
            while slug in anchors:  # a repeated heading gets -1, -2, ...
                slug = f"{_slug(heading.group(1))}-{n}"
                n += 1
            anchors.add(slug)
    return anchors


def _flags(command: str) -> set[str]:
    """The flags a documented command uses, before any comment."""
    return set(FLAG.findall(re.split(r"\s#", command)[0]))


def _code(text: str) -> tuple[list[str], list[str]]:
    """A document's prose lines and its fenced code lines, by CommonMark's fence rules: an
    opening run of three or more backticks (with no backtick after it) or tildes, closed by a
    run of the same character at least as long, alone on its line."""
    prose: list[str] = []
    code: list[str] = []
    fence = ""
    for line in text.splitlines():
        if not fence:
            opened = re.match(r" {0,3}(`{3,}(?=[^`]*$)|~{3,})", line)
            if opened:
                fence = opened.group(1)
            else:
                prose.append(line)
        elif re.fullmatch(rf" {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}\s*", line):
            fence = ""
        else:
            code.append(line)
    assert not fence, "the document ends inside a code block"
    return prose, code


def _commands(text: str) -> list[str]:
    """Each command a document shows: in a code span or a code block line, split at `&&`, `||`,
    `;` and `|`."""
    prose, code = _code(text)
    shown = [span for line in prose for span in re.findall(r"`([^`]+)`", line)] + code
    return [command.strip() for snippet in shown for command in re.split(r"&&|\|\||;|\|", snippet)]


def _options(parser: argparse.ArgumentParser) -> set[str]:
    return set(parser._option_string_actions)


def test_the_guide_installs_each_tool_at_its_pin() -> None:
    tools = load_machine_tools(ROOT / ".agents")
    guide = _text(GUIDE)

    for tool in tools.values():
        if tool.registry == "npm":
            spelled = re.compile(rf"(?<![\w/-]){re.escape(tool.package)}@([0-9][\w.]*)")
            assert spelled.search(guide), f"{GUIDE} doesn't install {tool.package}"
            for doc in CURRENT:
                for version in spelled.findall(_text(doc)):
                    assert version == tool.version, (
                        f"{doc}: {tool.package}@{version}, but the pin is {tool.version}"
                    )
        else:
            named = re.search(rf"\(`{tool.name}`\) ([0-9.]+)", guide)
            assert named and named.group(1) == tool.version, f"{GUIDE}: {tool.name}'s version"
            for asset in tool.assets.values():
                assert f"`{asset.file}`" in guide, f"{GUIDE} doesn't name {asset.file}"


def test_the_guides_npm_installs_wait_out_the_cooldown_as_the_script_does() -> None:
    tools = load_machine_tools(ROOT / ".agents")
    by_package = {tool.package: tool for tool in tools.values() if tool.registry == "npm"}
    installs = [c for c in _commands(_text(GUIDE)) if c.startswith("npm install -g") and "@" in c]

    assert len(installs) >= 2
    for install in installs:
        named = [by_package[p] for p in re.findall(r"(\S+)@[0-9]", install) if p in by_package]
        newest = max(datetime.fromisoformat(t.published_at.replace("Z", "+00:00")) for t in named)
        cutoff = f"{(newest.astimezone(UTC) + timedelta(days=1)).date()}T00:00:00Z"
        assert f" --before={cutoff} " in install, f"{GUIDE}: `{install}` needs --before={cutoff}"


def test_documented_commands_use_flags_that_exist() -> None:
    parser = _parser()
    commands = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ).choices
    script = set(FLAG.findall(SCRIPT.read_text().split("\nwhile [ $# -gt 0 ]")[1][:900]))
    assert {"--check", "--offline", "--yes", "--dir"} <= script
    known = script | _options(parser) | {f for c in commands.values() for f in _options(c)}
    checked = 0
    for doc in CURRENT:
        for command in _commands(_text(doc)):
            named = re.search(r"(?:^|[\s/])repo-template (new|update|check|globals)\b(.*)", command)
            found = named or re.match(r"(new|update|check|globals) (.*--.*)", command)
            if found:
                sub, rest = found.groups()
                unknown = _flags(rest) - _options(commands[sub])
            elif re.search(r"(?:^|[\s/])repo-template --", command):
                unknown = _flags(command.split("repo-template", 1)[1]) - _options(parser)
            elif "setup-machine.sh" in command:
                unknown = _flags(command.split("setup-machine.sh", 1)[1]) - script
            elif command.startswith("--"):  # a flag on its own: one of these, or another tool's
                unknown = _flags(command) - known - OTHER_TOOLS
            else:
                continue
            assert not unknown, f"{doc}: `{command}` uses {sorted(unknown)}"
            checked += 1
    assert checked > 60  # the patterns still find the commands


def test_the_ignore_entries_the_docs_list_are_the_ones_globals_writes() -> None:
    written = {line.removeprefix("**/") for line in GITIGNORE_CONTENT.splitlines()}
    last = sorted(written)[-1]
    found = 0
    for doc in CURRENT:
        for paragraph in re.split(r"\n\s*\n|\n\s*(?=[-*] |\d+\. )", _text(doc)):
            if f"`{last}`" in paragraph and "ignore" in paragraph:
                listed = set(re.findall(r"`(\.[\w-]+/)`", paragraph))
                assert listed == written, f"{doc}: {sorted(listed)} in {paragraph[:80]!r}"
                found += 1
    assert found >= 2  # the README's global linking, and the guide's Appendix A


@pytest.mark.parametrize("doc", DOCS)
def test_every_link_and_anchor_inside_the_repository_resolves(doc: str) -> None:
    source = ROOT / doc
    for target in LINK.findall(source.read_text()):
        if re.match(r"[a-z]+:", target):
            continue  # https:, mailto:
        path, _, anchor = target.partition("#")
        linked = (source.parent / path).resolve() if path else source
        assert linked.exists(), f"{doc}: {target} doesn't exist"
        if anchor:
            assert anchor in _anchors(linked), f"{doc}: {target}: no such heading"


def test_the_setup_scripts_links_into_the_guide_resolve() -> None:
    anchors = _anchors(ROOT / GUIDE)
    linked = re.findall(rf"(?:\$GUIDE|{re.escape(GUIDE)})#([\w-]+)", SCRIPT.read_text())
    sections = re.findall(r"section ([\d.]+) of \S*" + re.escape(GUIDE), SCRIPT.read_text())

    assert linked and sections
    for anchor in linked:
        assert anchor in anchors, f"setup-machine.sh links to #{anchor}"
    for section in sections:
        assert any(a.startswith(section.replace(".", "") + "-") for a in anchors), section
