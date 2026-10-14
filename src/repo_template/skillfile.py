"""Read and edit the YAML frontmatter at the top of a SKILL.md, without a YAML dependency.

Handles the forms skills use: `key: value`, quoted values, folded or literal block values
(blank lines included), and `#` comment lines, which YAML ignores. Lines end at CR, LF or CRLF
only, as in YAML, and every line keeps its own ending, so an edit changes nothing else.
"""

from __future__ import annotations

import json
import re

BLOCK_SCALARS = {">", ">-", "|", "|-"}
# The notice an override leaves in the file it changes (Apache-2.0 §4(b) asks for one in the
# file itself). A YAML comment, so no agent reads it as part of the skill.
CHANGE_NOTE_PREFIX = "# Changed by repo-template"
CHANGE_NOTE = CHANGE_NOTE_PREFIX + " (https://github.com/bennwitt/repo-template): {keys}. {origin}"
_LINE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+\Z")


def lines_of(text: str) -> list[str]:
    """The text's lines, each with its own ending."""
    return _LINE.findall(text)


def _strip(line: str) -> str:
    return line.rstrip("\r\n")


def _ending(line: str) -> str:
    return line[len(_strip(line)) :] or "\n"


def _bounds(lines: list[str]) -> tuple[int, int]:
    if not lines or lines[0] != "---":
        raise ValueError("SKILL.md must start with a --- frontmatter block")
    try:
        return 0, lines.index("---", 1)
    except ValueError:
        raise ValueError("SKILL.md frontmatter has no closing ---") from None


def _split(text: str) -> tuple[list[str], list[str], int]:
    """(lines with endings, lines without, index of the closing ---)."""
    lines = lines_of(text)
    stripped = [_strip(line) for line in lines]
    return lines, stripped, _bounds(stripped)[1]


def frontmatter_text(text: str) -> str:
    """The frontmatter between the --- lines, exactly as written."""
    lines, _, end = _split(text)
    return "".join(lines[1:end])


def _spans(stripped: list[str], end: int, key: str) -> list[tuple[int, int]]:
    """Every (start, stop) of a top-level field: its line and its indented continuation,
    through blank lines inside a block value."""
    spans = []
    for index in range(1, end):
        line = stripped[index]
        if line[:1] in {" ", "\t", "#"} or line.partition(":")[0].strip() != key:
            continue
        stop = probe = index + 1
        while probe < end:
            if stripped[probe][:1] in {" ", "\t"} and stripped[probe].strip():
                probe += 1
                stop = probe
            elif not stripped[probe].strip():
                probe += 1
            else:
                break
        spans.append((index, stop))
    return spans


def field_count(text: str, key: str) -> int:
    _, stripped, end = _split(text)
    return len(_spans(stripped, end, key))


def read_fields(text: str) -> dict[str, str]:
    """Return the frontmatter's top-level fields as strings."""
    _, lines, end = _split(text)
    fields: dict[str, str] = {}
    key = ""
    for line in lines[1:end]:
        if line[:1] == "#":
            continue
        if line[:1] in {" ", "\t"} and key:
            if line.strip():  # a blank line inside a block value adds nothing
                more = line.strip()
                fields[key] = f"{fields[key]} {more}" if fields[key] else more
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value in BLOCK_SCALARS:
            value = ""
        elif len(value) >= 2 and value[0] == value[-1] == '"':
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = value[1:-1]
        elif len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1].replace("''", "'")
        fields[key] = value
    return fields


def format_value(value: str | bool) -> str:
    """Render a value as YAML: booleans bare, strings double-quoted (JSON is valid YAML)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value, ensure_ascii=False)


def field_lines(text: str, key: str) -> str | None:
    """A field exactly as written, line endings included, or None if it is absent."""
    lines, stripped, end = _split(text)
    spans = _spans(stripped, end, key)
    return "".join(lines[spans[0][0] : spans[0][1]]) if spans else None


def restore_field(text: str, key: str, raw: str | None) -> str:
    """Put a field back as `field_lines` returned it; None removes it. A field that is absent
    goes just before the closing ---."""
    lines, stripped, end = _split(text)
    replacement = [] if raw is None else [raw]
    spans = _spans(stripped, end, key)
    if not spans:
        return "".join([*lines[:end], *replacement, *lines[end:]])
    start, stop = spans[0]
    return "".join([*lines[:start], *replacement, *lines[stop:]])


def set_field(text: str, key: str, value: str | bool) -> str:
    """Set a top-level frontmatter field, replacing its old value and any continuation lines,
    with the line ending of the line it replaces (or of the line above the closing ---)."""
    lines, stripped, end = _split(text)
    spans = _spans(stripped, end, key)
    ending = _ending(lines[spans[0][1] - 1] if spans else lines[end - 1])
    return restore_field(text, key, f"{key}: {format_value(value)}{ending}")


def has_change_note(text: str) -> bool:
    _, stripped, end = _split(text)
    return any(line.startswith(CHANGE_NOTE_PREFIX) for line in stripped[1:end])


def without_change_note(text: str) -> str:
    lines, stripped, end = _split(text)
    return "".join(
        line
        for index, line in enumerate(lines)
        if not (0 < index < end and stripped[index].startswith(CHANGE_NOTE_PREFIX))
    )


def with_change_note(text: str, keys: list[str], origin: str) -> str:
    """The text with a change note, naming the changed fields and where the original is,
    before the closing ---."""
    lines, _, end = _split(text)
    note = CHANGE_NOTE.format(keys=", ".join(keys), origin=origin) + _ending(lines[end - 1])
    return "".join([*lines[:end], note, *lines[end:]])
