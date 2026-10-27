"""Read-only catalog presentation and a terminal picker; neither writes repository state."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from repo_template.resolve import visible
from repo_template.selection import Selection
from repo_template.skillfile import read_fields
from repo_template.standards import load_skill_packs


@dataclass(frozen=True)
class Entry:
    kind: str
    name: str
    description: str
    skills: tuple[str, ...] = ()
    packs: tuple[str, ...] = ()
    mcp: tuple[str, ...] = ()
    global_skill: bool = False

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.name}"


def entries(agents: Path) -> list[Entry]:
    definitions = load_skill_packs(agents)
    source = agents / "skill-packs.json"
    raw = json.loads(source.read_text()) if source.is_file() else {}
    result: list[Entry] = []
    for name, skills in sorted(definitions.items()):
        info = raw[name]
        mcp = tuple(
            item if isinstance(item, str) else item["server"] for item in info.get("mcp", [])
        )
        result.append(Entry("pack", name, str(info.get("description", "")), tuple(skills), mcp=mcp))
    for folder, global_skill in (("packs", False), ("skills", True)):
        directory = agents / folder
        if not directory.is_dir():
            continue
        for skill in sorted(directory.iterdir()):
            path = skill / "SKILL.md"
            if not path.is_file() or skill.name == "synced":
                continue
            description = read_fields(path.read_text()).get("description", "")
            result.append(
                Entry(
                    "skill",
                    skill.name,
                    description,
                    packs=tuple(
                        name for name, skills in sorted(definitions.items()) if skill.name in skills
                    ),
                    global_skill=global_skill,
                )
            )
    return result


def selected(entry: Entry, selection: Selection) -> bool:
    return entry.name in (selection.packs if entry.kind == "pack" else selection.skills)


def detail(entry: Entry, selection: Selection) -> str:
    if entry.kind == "pack":
        return (
            "skills: "
            + ", ".join(entry.skills)
            + ("; MCP: " + ", ".join(entry.mcp) if entry.mcp else "")
        )
    if entry.global_skill:
        return "global; installed by globals"
    via = sorted(set(entry.packs) & set(selection.packs))
    return (
        "via selected pack: " + ", ".join(via)
        if via
        else "packs: " + (", ".join(entry.packs) or "none")
    )


def show_catalog(agents: Path, mode: str, selection: Selection, *, json_output: bool) -> None:
    rows = [e for e in entries(agents) if mode == "all" or e.kind + "s" == mode]
    if json_output:
        print(
            json.dumps(
                {
                    "catalog": str(agents),
                    "selection": asdict(selection),
                    "entries": [
                        dict(
                            asdict(e),
                            selected=selected(e, selection),
                            supplied_by=sorted(set(e.packs) & set(selection.packs)),
                        )
                        for e in rows
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    print(visible(f"Catalog: {agents}"))
    for entry in rows:
        mark = "x" if selected(entry, selection) else " "
        print(visible(f"[{mark}] {entry.key} — {entry.description}"))
        print(visible(f"    {detail(entry, selection)}"))


def choose(agents: Path, initial: Selection) -> Selection | None:
    rows = [e for e in entries(agents) if not e.global_skill]
    known = {e.key for e in rows}
    for kind, names in (("pack", initial.packs), ("skill", initial.skills)):
        rows.extend(
            Entry(kind, name, "Missing from catalog; deselect to remove")
            for name in names
            if f"{kind}:{name}" not in known
        )
    choices = {e.key for e in rows if selected(e, initial)}
    print(visible(f"Catalog: {agents}"))
    print("Toggle numbers or pack:NAME / skill:NAME (space/comma separated).")
    print("View: packs, skills, all, /search. done previews; q cancels. Global skills use globals.")
    view = "packs"
    while True:
        current = Selection(
            tuple(sorted(k[5:] for k in choices if k.startswith("pack:"))),
            tuple(sorted(k[6:] for k in choices if k.startswith("skill:"))),
        )
        for i, e in enumerate(rows, 1):
            matches = (
                view == "all"
                or view == e.kind + "s"
                or (
                    view.startswith("/")
                    and view[1:].casefold()
                    in f"{e.key} {e.description} {' '.join(e.skills)}".casefold()
                )
            )
            if matches:
                print(
                    visible(f"{i:3} [{'x' if e.key in choices else ' '}] {e.key} — {e.description}")
                )
                print(visible(f"      {detail(e, current)}"))
        answer = input("Selection> ").strip()
        if answer in ("q", "quit"):
            return None
        if answer == "done":
            return current
        if answer in ("packs", "skills", "all") or answer.startswith("/"):
            view = answer
            continue
        tokens = answer.replace(",", " ").split()
        keys = [
            rows[int(t) - 1].key if t.isdigit() and 1 <= int(t) <= len(rows) else t for t in tokens
        ]
        if not keys or any(key not in {e.key for e in rows} for key in keys):
            print("Use a listed number, pack:NAME or skill:NAME; done previews; q cancels.")
            continue
        choices.symmetric_difference_update(set(keys))
