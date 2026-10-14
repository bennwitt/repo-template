"""Portable Claude Code settings, merged into ~/.claude/settings.json instead of linked.

The standards repository keeps `.agents/claude-settings.json`:

    {"portable": {...}, "defaults": {...}, "linked": {...}}

`portable` entries belong to repo-template, one by one: each plugin switch, environment variable
and marketplace, each permission rule, and each hook (identified by its event, matcher and
command). `globals` keeps them current with a three-way merge against what it last wrote on this
machine (`~/.repo-template/globals-state.json`): an entry still as written takes the new value,
an entry the person changed here is kept and reported (again only if the standard's value then
changes), and nothing else in the file is touched.

`defaults` (model, effort, theme, notifications) are written once, when a machine doesn't have
them, and never again: they belong to the machine. `linked` is what the pre-0.4.2 link
distributed; it is used only to migrate that link into a merged file.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from repo_template.model import Result

SOURCE_NAME = "claude-settings.json"
STATE_NAME = ".repo-template/globals-state.json"
STATE_VERSION = 2
LEGACY_LINK_TARGET = ".claude/settings.json"  # where the pre-0.4.2 link pointed, in the standards
MAP_SECTIONS = {"enabledPlugins": bool, "env": str, "extraKnownMarketplaces": dict}
RULE_LISTS = ("ask", "deny")  # "allow" widens access, so it is never distributed
# Machine preferences `defaults` may set. Anything else (permissions, hooks, bypass modes,
# auto-approved MCP servers, remote control) would widen access on every new machine.
DEFAULT_KEYS = frozenset(
    {"model", "effortLevel", "modelSettings", "theme", "outputStyle", "agentPushNotifEnabled"}
)
RULE = re.compile(r"[A-Za-z][\w*-]*(\(.+\))?")
ABSENT: Any = object()


def _canonical(value: Any) -> str:
    if value is ABSENT:
        return "absent"
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _matcher_key(matcher: Any) -> str:
    """None, "" and "*" all match every tool, so they are one group."""
    return "*" if matcher in (None, "", "*") else str(matcher)


def _check_portable(portable: dict[str, Any], where: str) -> None:
    unknown = set(portable) - {*MAP_SECTIONS, "permissions", "hooks"}
    _require(not unknown, f"{where} can't own {sorted(unknown)}")
    for section, kind in MAP_SECTIONS.items():
        values = portable.get(section, {})
        _require(isinstance(values, dict), f"{where}.{section} must be an object")
        for key, value in values.items():
            _require(isinstance(value, kind), f"{where}.{section}.{key} must be a {kind.__name__}")
    permissions = portable.get("permissions", {})
    _require(isinstance(permissions, dict), f"{where}.permissions must be an object")
    _require("allow" not in permissions, f"{where}.permissions.allow widens access; never shared")
    for name, rules in permissions.items():
        _require(name in RULE_LISTS, f"{where}.permissions.{name} isn't a rule list")
        _require(isinstance(rules, list), f"{where}.permissions.{name} must be a list")
        for rule in rules:
            _require(
                isinstance(rule, str) and RULE.fullmatch(rule) is not None,
                f"{where}.permissions.{name}: {rule!r} isn't a permission rule",
            )
    hooks = portable.get("hooks", {})
    _require(isinstance(hooks, dict), f"{where}.hooks must be an object")
    for event, groups in hooks.items():
        _require(isinstance(groups, list), f"{where}.hooks.{event} must be a list")
        for group in groups:
            _require(
                isinstance(group, dict) and isinstance(group.get("hooks"), list),
                f"{where}.hooks.{event} groups need a 'hooks' list",
            )
            for hook in group["hooks"]:
                command = hook.get("command") if isinstance(hook, dict) else None
                _require(
                    isinstance(command, str) and command.rstrip().endswith("|| true"),
                    f"{where}.hooks.{event}: every hook needs a command ending in '|| true' so it "
                    "can never block a session",
                )


def load_source(standards_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Read and validate (portable, defaults, linked) from the standards repository."""
    path = standards_root / ".agents" / SOURCE_NAME
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    _require(isinstance(raw, dict), f"{path} must hold a JSON object")
    portable, defaults, linked = (raw.get(key, {}) for key in ("portable", "defaults", "linked"))
    for name, value in (("portable", portable), ("defaults", defaults), ("linked", linked)):
        _require(isinstance(value, dict), f"{path}: '{name}' must be an object")
    _check_portable(portable, f"{path}: portable")
    widening = set(defaults) - DEFAULT_KEYS
    _require(
        not widening,
        f"{path}: 'defaults' may only set {sorted(DEFAULT_KEYS)}, not {sorted(widening)}: "
        "anything else could widen access on every new machine",
    )
    return portable, defaults, linked


# The units portable settings own, by label. The label is used in reports and in the state file.


def _entries(portable: dict[str, Any]) -> dict[str, tuple[str, str, Any]]:
    return {
        f"{section}.{key}": (section, key, value)
        for section in MAP_SECTIONS
        for key, value in portable.get(section, {}).items()
    }


def _rules(portable: dict[str, Any]) -> dict[str, tuple[str, str]]:
    permissions = portable.get("permissions", {})
    return {
        f"permissions.{name} {rule}": (name, rule)
        for name in RULE_LISTS
        for rule in permissions.get(name, [])
    }


def _hooks(portable: dict[str, Any]) -> dict[str, list[Any]]:
    """label -> [event, matcher as given, hook]. A hook is identified by its command, so an edit
    to its other fields (a timeout) is a change to the same hook."""
    owned: dict[str, list[Any]] = {}
    for event, groups in portable.get("hooks", {}).items():
        for group in groups if isinstance(groups, list) else []:
            hooks = group.get("hooks", []) if isinstance(group, dict) else []
            for hook in hooks if isinstance(hooks, list) else []:
                command = hook.get("command") if isinstance(hook, dict) else None
                if isinstance(command, str):
                    label = f"hooks.{event} {_matcher_key(group.get('matcher'))} {command}"
                    owned[label] = [event, group.get("matcher"), hook]
    return owned


class _Merge:
    """Apply portable settings to `settings` in place, recording what changed and was kept."""

    def __init__(self, settings: dict[str, Any], state: dict[str, Any]) -> None:
        self.settings = settings
        self.applied: dict[str, Any] = dict(state.get("applied", {}))
        self.kept: dict[str, str] = dict(state.get("kept", {}))
        self.new_applied: dict[str, Any] = {}
        self.seen: set[str] = set()
        self.changes: list[str] = []
        self.preserved: list[str] = []
        self.existed = {key for key, value in settings.items() if isinstance(value, dict)}
        self.emptied: set[str] = set()

    def _object(self, key: str) -> dict[str, Any]:
        value = self.settings.setdefault(key, {})
        if not isinstance(value, dict):
            raise ValueError(f"'{key}' in Claude settings must be an object")
        return value

    def _list(self, parent: dict[str, Any], key: str, where: str) -> list[Any]:
        value = parent.setdefault(key, [])
        if not isinstance(value, list):
            raise ValueError(f"'{where}' in Claude settings must be a list")
        return value

    def _value(self, label: str, have: Any, want: Any, apply: Any) -> None:
        """The three-way decision for one owned value. `apply(value)` writes it (ABSENT removes)."""
        self.seen.add(label)
        was = self.applied.get(label, ABSENT)
        if have is not ABSENT and want is not ABSENT and have == want:
            self.kept.pop(label, None)
            if label in self.applied:  # ours; a value the person already had is never claimed
                self.new_applied[label] = want
            return
        if have is ABSENT and want is ABSENT:
            self.kept.pop(label, None)
            return
        if _same(have, was):
            apply(want)
            self.changes.append(f"{label} (removed)" if want is ABSENT else label)
            self.kept.pop(label, None)
            if want is not ABSENT:
                self.new_applied[label] = want
            return
        # Changed on this machine: keep it. Report it, and again whenever the standard's value
        # for it changes, but not on every run.
        marker = _canonical([_canonical(have), _canonical(want)])
        if self.kept.get(label) != marker:
            what = "removed on this machine" if have is ABSENT else "changed on this machine; kept"
            self.preserved.append(f"{label} ({what})")
        self.kept[label] = marker
        if want is not ABSENT:
            self.new_applied[label] = want

    def entry(self, label: str, section: str, key: str, want: Any) -> None:
        current = self._object(section)

        def apply(value: Any) -> None:
            if value is ABSENT:
                del current[key]
                if not current:
                    self.emptied.add(section)
            else:
                current[key] = value

        self._value(label, current.get(key, ABSENT), want, apply)

    def rule(self, label: str, name: str, rule: str, wanted: bool) -> None:
        permissions = self._object("permissions")
        existed = name in permissions
        rules = self._list(permissions, name, f"permissions.{name}")

        def apply(value: Any) -> None:
            if value is ABSENT:
                rules.remove(rule)
            else:
                rules.append(rule)

        self._value(label, True if rule in rules else ABSENT, True if wanted else ABSENT, apply)
        if not rules and (not existed or label in self.applied):
            permissions.pop(name)
            self.emptied.add("permissions")

    def hook(self, label: str, event: str, matcher: Any, want: Any) -> None:
        events = self._object("hooks")
        existed = event in events
        groups = self._list(events, event, f"hooks.{event}")
        key = _matcher_key(matcher)
        group = next(
            (g for g in groups if isinstance(g, dict) and _matcher_key(g.get("matcher")) == key),
            None,
        )
        hooks = group.get("hooks") if isinstance(group, dict) else None
        command = label.split(" ", 2)[2]
        index = next(
            (
                i
                for i, hook in enumerate(hooks if isinstance(hooks, list) else [])
                if isinstance(hook, dict) and hook.get("command") == command
            ),
            None,
        )
        have = hooks[index] if isinstance(hooks, list) and index is not None else ABSENT

        def apply(value: Any) -> None:
            nonlocal group
            if value is ABSENT:
                if group is not None and isinstance(hooks, list) and index is not None:
                    hooks.pop(index)
                    if not hooks:
                        groups.remove(group)
                return
            if group is None:
                group = {"hooks": []} if matcher is None else {"matcher": matcher, "hooks": []}
                groups.append(group)
            target = self._list(group, "hooks", f"hooks.{event}")
            if index is not None and target is hooks:
                target[index] = value
            else:
                target.append(value)

        self._value(label, have, want, apply)
        if not groups and (not existed or label in self.applied):
            events.pop(event)
            self.emptied.add("hooks")

    def finish(self) -> None:
        for key in ("permissions", "hooks", *MAP_SECTIONS):
            if self.settings.get(key) == {} and (key not in self.existed or key in self.emptied):
                del self.settings[key]
        self.kept = {label: value for label, value in self.kept.items() if label in self.seen}


def _same(left: Any, right: Any) -> bool:
    if left is ABSENT or right is ABSENT:
        return left is right
    return bool(left == right)


def merge_portable(
    settings: dict[str, Any],
    desired: dict[str, Any],
    state: dict[str, Any],
    defaults: dict[str, Any],
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Apply `desired` to `settings` in place. Returns (changes, preserved, new state)."""
    merge = _Merge(settings, state)
    entries, rules, hooks = _entries(desired), _rules(desired), _hooks(desired)
    applied = merge.applied

    def in_order(owned: dict[str, Any], prefix: tuple[str, ...]) -> list[str]:
        """The source's order first (as written into a fresh file), then entries it dropped."""
        dropped = sorted(k for k in applied if k.startswith(prefix) and k not in owned)
        return [*owned, *dropped]

    for label in in_order(entries, tuple(f"{section}." for section in MAP_SECTIONS)):
        section, key = label.split(".", 1)
        merge.entry(label, section, key, entries[label][2] if label in entries else ABSENT)
    for label in in_order(rules, ("permissions.",)):
        name, rule = label[len("permissions.") :].split(" ", 1)
        merge.rule(label, name, rule, label in rules)
    previous = state.get("hook_values", {})
    for label in in_order(hooks, ("hooks.",)):
        event, matcher, hook = hooks.get(label) or previous.get(label) or (None, None, None)
        if event is not None:
            merge.hook(label, event, matcher, hook if label in hooks else ABSENT)
    merge.finish()
    written = {key for key in state.get("defaults_written", []) if isinstance(key, str)}
    for key, value in defaults.items():
        if key not in settings and key not in written:
            settings[key] = value
            merge.changes.append(f"{key} (machine default)")
        written.add(key)
    new_state = {
        "version": STATE_VERSION,
        "applied": merge.new_applied,
        "kept": merge.kept,
        "defaults_written": sorted(written),
        "hook_values": {label: hooks[label] for label in hooks if label in merge.new_applied},
    }
    return merge.changes, merge.preserved, new_state


def _owned_by(linked: dict[str, Any]) -> dict[str, Any]:
    """State for a file that holds what `linked` distributed: all of it was written by us."""
    applied: dict[str, Any] = {label: value for label, (_, _, value) in _entries(linked).items()}
    applied.update(dict.fromkeys(_rules(linked), True))
    hooks = _hooks(linked)
    applied.update({label: value[2] for label, value in hooks.items()})
    return {"applied": applied, "kept": {}, "defaults_written": [], "hook_values": hooks}


def _looks_distributed(settings: dict[str, Any], linked: dict[str, Any]) -> bool:
    """A real file with no state that still holds every rule and hook the old link distributed
    (someone replaced the link by hand): it came from repo-template."""
    rules, hooks = set(_rules(linked)), set(_hooks(linked))
    if not rules and not hooks:
        return False
    permissions = settings.get("permissions", {})
    lists = permissions if isinstance(permissions, dict) else {}
    have: set[str] = set()
    for name in RULE_LISTS:
        listed = lists.get(name)
        if isinstance(listed, list):
            have |= {f"permissions.{name} {rule}" for rule in listed}
    have |= set(_hooks({"hooks": settings.get("hooks", {})}))
    return rules | hooks <= have


def _record(whole_state: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """This machine's claude_settings state, converted from version 1 if needed."""
    record = json.loads(json.dumps(whole_state.get("claude_settings", {})))  # a private copy
    if not isinstance(record, dict):
        raise ValueError("claude_settings must be an object")
    if record and record.get("version") != STATE_VERSION:
        # Version 1 recorded the whole portable object it applied, not entry by entry.
        applied = record.get("applied")
        if not isinstance(applied, dict):
            raise ValueError("a version 1 record needs an 'applied' object")
        _check_portable(applied, "applied")
        return {**_owned_by(applied), "defaults_written": sorted(defaults)}
    applied, kept = record.get("applied", {}), record.get("kept", {})
    written, hooks = record.get("defaults_written", []), record.get("hook_values", {})
    _require(isinstance(applied, dict) and isinstance(kept, dict), "applied/kept must be objects")
    _require(all(isinstance(value, str) for value in kept.values()), "kept values must be text")
    _require(isinstance(written, list) and all(isinstance(k, str) for k in written), "defaults")
    _require(
        isinstance(hooks, dict)
        and all(isinstance(value, list) and len(value) == 3 for value in hooks.values()),
        "hook_values must map labels to [event, matcher, hook]",
    )
    return record


def read_state(home: Path) -> dict[str, Any]:
    path = home / STATE_NAME
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    return value if isinstance(value, dict) else {}


def write_state(home: Path, state: dict[str, Any]) -> None:
    path = home / STATE_NAME
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    _write_private(path, json.dumps(state, indent=2, sort_keys=True) + "\n", mode=0o600)


def _write_private(path: Path, content: str, *, mode: int, expected: bytes | None = None) -> None:
    """Write atomically through a temp file that is private from the start. With `expected`,
    refuse when the file no longer holds the bytes that were read (Claude Code wrote meanwhile)."""
    temporary = path.with_name(f".{path.name}.repo-template-tmp")
    temporary.unlink(missing_ok=True)
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
        os.chmod(temporary, mode)
        if expected is not None:
            current = path.read_bytes() if path.exists() else None
            if current != expected:
                raise ValueError(f"{path} changed while globals was merging it; run it again")
        os.replace(temporary, path)  # replaces a link itself, never its target
    finally:
        temporary.unlink(missing_ok=True)


def _backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(source.read_bytes())


def _is_legacy_link(path: Path, standards_root: Path) -> bool:
    target = Path(os.readlink(path))
    if not target.is_absolute():
        target = path.parent / target
    legacy = standards_root / LEGACY_LINK_TARGET
    try:
        return target.parent.resolve() / target.name == legacy.parent.resolve() / legacy.name
    except OSError:
        return False


def sync_claude_settings(
    standards_root: Path, home: Path, result: Result, *, check: bool, stamp: str
) -> None:
    """Merge the portable settings into ~/.claude/settings.json (see the module docstring)."""
    desired, defaults, linked = load_source(standards_root)
    path = home / ".claude/settings.json"
    label = str(path)
    state_path = home / STATE_NAME
    try:
        whole_state = read_state(home)
        record = _record(whole_state, defaults)
    except (ValueError, AttributeError, TypeError, KeyError) as exc:
        result.errors.append(f"{state_path} can't be used ({exc}); delete it to reset")
        return
    migrating = path.is_symlink()
    if migrating and not _is_legacy_link(path, standards_root):
        target = os.readlink(path)
        if whole_state.get("foreign_link") == target:
            result.unchanged.append(label)  # reported before, and still the same link
            return
        result.preserved.append(
            f"{label} (a link to {target}, which repo-template didn't create; left alone: "
            "replace it with a file to have globals merge into it)"
        )
        if not check:
            write_state(home, {**whole_state, "foreign_link": target})
        return
    original: bytes | None = None
    try:
        if migrating:
            try:
                text = path.read_text()  # this machine's view through the old link
                record = _owned_by(linked)
            except OSError:
                text, record = "{}", {}  # left dangling by a pull: a fresh machine
        elif path.exists():
            original = path.read_bytes()
            text = original.decode()
        else:
            text, record = "{}", {}  # a fresh machine
        settings = json.loads(text or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        result.errors.append(f"{label} isn't valid JSON ({exc}); nothing was merged")
        return
    if not isinstance(settings, dict):
        result.errors.append(f"{label} must hold a JSON object; nothing was merged")
        return
    if not migrating and not record.get("applied") and _looks_distributed(settings, linked):
        record = _owned_by(linked)
    before = _canonical(settings)
    try:
        changes, preserved, new_record = merge_portable(settings, desired, record, defaults)
    except ValueError as exc:
        result.errors.append(f"{label}: {exc}")
        return
    result.preserved.extend(f"{label} {item}" for item in preserved)
    reports = [f"{label} {change}" for change in changes]
    if migrating:
        note = "becomes a merged file"
        if settings.get("remoteControlAtStartup"):
            note += "; remoteControlAtStartup, once shared, is now this machine's own setting"
        reports.insert(0, f"{label} (a link to {os.readlink(path)}; {note})")
    new_state = {**whole_state, "claude_settings": new_record}
    new_state.pop("foreign_link", None)
    if not migrating and _canonical(settings) == before:
        result.unchanged.append(label)
        if not check and _canonical(new_state) != _canonical(whole_state):
            write_state(home, new_state)
        return
    if check:
        result.updated.extend(reports)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = home / ".repo-template/backups" / stamp / ".claude/settings.json"
    if migrating:
        backup.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        backup.with_name("settings.json.link").write_text(os.readlink(path) + "\n")
    if path.exists():  # a link's content too: its target goes away with the pull
        _backup(path, backup)
    mode = 0o600 if migrating or not path.exists() else path.stat().st_mode & 0o777
    try:
        _write_private(path, json.dumps(settings, indent=2) + "\n", mode=mode, expected=original)
    except (ValueError, OSError) as exc:
        result.errors.append(str(exc))
        return
    result.updated.extend(reports)
    write_state(home, new_state)
