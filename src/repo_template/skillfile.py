"""Read and edit the YAML frontmatter at the top of a SKILL.md, without a YAML dependency.

Handles the forms skills use: `key: value`, quoted values, and folded or literal block values.
"""

from __future__ import annotations

import json

BLOCK_SCALARS = {">", ">-", "|", "|-"}


def _bounds(lines: list[str]) -> tuple[int, int]:
    if not lines or lines[0] != "---":
        raise ValueError("SKILL.md must start with a --- frontmatter block")
    return 0, lines.index("---", 1)


def read_fields(text: str) -> dict[str, str]:
    """Return the frontmatter's top-level fields as strings."""
    lines = text.splitlines()
    start, end = _bounds(lines)
    fields: dict[str, str] = {}
    key = ""
    for line in lines[start + 1 : end]:
        if line[:1] in {" ", "\t"} and key:
            fields[key] = f"{fields[key]} {line.strip()}".strip()
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


def set_field(text: str, key: str, value: str | bool) -> str:
    """Set a top-level frontmatter field, replacing its old value and any continuation lines."""
    lines = text.splitlines(keepends=True)
    stripped = [line.rstrip("\n") for line in lines]
    start, end = _bounds(stripped)
    rendered = f"{key}: {format_value(value)}\n"
    for index in range(start + 1, end):
        if stripped[index].partition(":")[0].strip() == key and stripped[index][:1] not in " \t":
            stop = index + 1
            while stop < end and stripped[stop][:1] in {" ", "\t"}:
                stop += 1
            return "".join([*lines[:index], rendered, *lines[stop:]])
    return "".join([*lines[:end], rendered, *lines[end:]])
