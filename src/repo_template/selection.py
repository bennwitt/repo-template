"""Explicit repository choices, separate from the skills supplied by a whole pack."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


def _names(values: object, label: str) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or not all(
        isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name)
        for name in values
    ):
        raise ValueError(f"{label} must be a list of skill/pack names")
    return tuple(sorted(set(values)))


@dataclass(frozen=True)
class Selection:
    packs: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()

    @classmethod
    def from_manifest(cls, manifest: Mapping[str, object]) -> Selection:
        return cls(
            _names(manifest.get("skill_packs", []), "skill_packs"),
            _names(manifest.get("individual_skills", []), "individual_skills"),
        )

    def change(
        self,
        packs: Sequence[str] = (),
        skills: Sequence[str] = (),
        remove_packs: Sequence[str] = (),
        remove_skills: Sequence[str] = (),
    ) -> Selection:
        additions = (_names(list(packs), "packs"), _names(list(skills), "skills"))
        removals = (
            _names(list(remove_packs), "remove packs"),
            _names(list(remove_skills), "remove skills"),
        )
        for added, removed in zip(additions, removals, strict=True):
            if set(added) & set(removed):
                raise ValueError("cannot add and remove the same selection in one command")
        return Selection(
            tuple(sorted((set(self.packs) | set(additions[0])) - set(removals[0]))),
            tuple(sorted((set(self.skills) | set(additions[1])) - set(removals[1]))),
        )


def require_skills(skills: Sequence[str], agents_dir: Path) -> None:
    for name in _names(list(skills), "skills"):
        if (agents_dir / "packs" / name / "SKILL.md").is_file():
            continue
        if (agents_dir / "skills" / name / "SKILL.md").is_file():
            raise ValueError(f"{name} is a global skill; use `repo-template globals` to install it")
        raise ValueError(
            f"unknown individual skill: {name}; see `repo-template globals --list skills`"
        )
