"""Portable Claude settings are merged into ~/.claude/settings.json, never linked (0.4.2+)."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from repo_template import settings as settings_module
from repo_template.model import Result
from repo_template.settings import load_source, sync_claude_settings

ROOT = Path(__file__).resolve().parents[1]

HOOK = {"matcher": "Skill", "hooks": [{"type": "command", "command": "receipt || true"}]}


def _standards(
    root: Path,
    portable: dict[str, Any],
    defaults: dict[str, Any] | None = None,
    linked: dict[str, Any] | None = None,
) -> Path:
    (root / ".agents").mkdir(parents=True, exist_ok=True)
    source = {"portable": portable, "defaults": defaults or {}, "linked": linked or {}}
    (root / ".agents/claude-settings.json").write_text(json.dumps(source))
    return root


def _sync(standards: Path, home: Path, *, check: bool = False) -> Result:
    result = Result(standards)
    sync_claude_settings(standards, home, result, check=check, stamp="stamp")
    return result


def _settings(home: Path) -> dict[str, Any]:
    return json.loads((home / ".claude/settings.json").read_text())


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_a_fresh_machine_gets_portable_settings_and_defaults(tmp_path: Path) -> None:
    standards = _standards(
        tmp_path / "s",
        {"enabledPlugins": {"a@m": True}, "hooks": {"PostToolUse": [HOOK]}},
        {"model": "opus"},
    )
    home = tmp_path / "home"

    _sync(standards, home)

    assert _settings(home) == {
        "enabledPlugins": {"a@m": True},
        "hooks": {"PostToolUse": [HOOK]},
        "model": "opus",
    }
    assert _mode(home / ".claude/settings.json") == 0o600
    assert _mode(home / ".repo-template/globals-state.json") == 0o600
    assert not _sync(standards, home).needs_attention  # idempotent


def test_the_old_link_becomes_a_merged_file_and_portable_changes_apply(tmp_path: Path) -> None:
    """Before 0.4.2 the file was a link to the standards repository's copy."""
    old = tmp_path / "s/.claude/settings.json"
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps({"enabledPlugins": {"azure@m": True}, "model": "opus[1m]"}))
    standards = _standards(
        tmp_path / "s",
        {"enabledPlugins": {"azure@m": False}},
        linked={"enabledPlugins": {"azure@m": True}},  # what the link distributed
    )
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").symlink_to(old)

    planned = _sync(standards, home, check=True)
    assert (home / ".claude/settings.json").is_symlink()
    assert any("becomes a merged file" in item for item in planned.updated)

    _sync(standards, home)

    path = home / ".claude/settings.json"
    assert not path.is_symlink()
    assert _settings(home) == {"enabledPlugins": {"azure@m": False}, "model": "opus[1m]"}
    backup = home / ".repo-template/backups/stamp/.claude/settings.json"
    assert json.loads(backup.read_text())["enabledPlugins"] == {"azure@m": True}  # the content
    assert backup.with_name("settings.json.link").read_text().strip() == str(old)


def test_a_portable_change_reaches_an_untouched_entry(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"enabledPlugins": {"azure@m": True}})
    home = tmp_path / "home"
    _sync(standards, home)
    _standards(standards, {"enabledPlugins": {"azure@m": False}})

    result = _sync(standards, home)

    assert result.updated == [f"{home}/.claude/settings.json enabledPlugins.azure@m"]
    assert _settings(home)["enabledPlugins"] == {"azure@m": False}


def test_an_entry_changed_on_this_machine_is_kept_and_reported_once(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"enabledPlugins": {"azure@m": True}})
    home = tmp_path / "home"
    _sync(standards, home)
    data = _settings(home)
    data["enabledPlugins"]["azure@m"] = False  # turned off with /plugin here
    (home / ".claude/settings.json").write_text(json.dumps(data))

    first = _sync(standards, home)
    second = _sync(standards, home)

    assert first.preserved == [
        f"{home}/.claude/settings.json enabledPlugins.azure@m (changed on this machine; kept)"
    ]
    assert not second.needs_attention
    assert _settings(home)["enabledPlugins"] == {"azure@m": False}


def test_a_changed_hook_replaces_the_old_one_instead_of_adding_a_second(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"hooks": {"PostToolUse": [HOOK]}})
    home = tmp_path / "home"
    _sync(standards, home)
    newer = {"matcher": "Skill", "hooks": [{"type": "command", "command": "receipt2 || true"}]}
    _standards(standards, {"hooks": {"PostToolUse": [newer]}})

    _sync(standards, home)

    assert _settings(home)["hooks"] == {"PostToolUse": [newer]}


def test_rules_dropped_from_portable_are_removed_but_the_persons_own_are_kept(
    tmp_path: Path,
) -> None:
    standards = _standards(tmp_path / "s", {"permissions": {"deny": ["Read(./.env)", "old"]}})
    home = tmp_path / "home"
    _sync(standards, home)
    data = _settings(home)
    data["permissions"]["deny"].append("Read(./mine)")
    (home / ".claude/settings.json").write_text(json.dumps(data))
    _standards(standards, {"permissions": {"deny": ["Read(./.env)"]}})

    _sync(standards, home)

    assert _settings(home)["permissions"]["deny"] == ["Read(./.env)", "Read(./mine)"]


def test_a_portable_rule_removed_on_this_machine_stays_removed(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"permissions": {"ask": ["Bash(docker *rmi *)"]}})
    home = tmp_path / "home"
    _sync(standards, home)
    data = _settings(home)
    del data["permissions"]
    (home / ".claude/settings.json").write_text(json.dumps(data))

    first = _sync(standards, home)
    second = _sync(standards, home)

    assert "removed on this machine" in first.preserved[0]
    assert not second.needs_attention
    assert "permissions" not in _settings(home)


def test_an_existing_file_never_written_by_globals_keeps_its_values(tmp_path: Path) -> None:
    standards = _standards(
        tmp_path / "s", {"enabledPlugins": {"a@m": True, "b@m": True}}, {"model": "opus"}
    )
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    mine = {"enabledPlugins": {"a@m": False}, "model": "sonnet", "theme": "dark"}
    (home / ".claude/settings.json").write_text(json.dumps(mine))
    os.chmod(home / ".claude/settings.json", 0o644)

    result = _sync(standards, home)

    assert _settings(home) == {
        "enabledPlugins": {"a@m": False, "b@m": True},
        "model": "sonnet",
        "theme": "dark",
    }
    assert len(result.preserved) == 1 and "a@m" in result.preserved[0]
    assert _mode(home / ".claude/settings.json") == 0o644  # its own mode is kept
    assert (home / ".repo-template/backups/stamp/.claude/settings.json").is_file()


def test_invalid_json_is_reported_and_left_alone(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"env": {"A": "1"}})
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text("{ nope")

    result = _sync(standards, home)

    assert result.errors and "isn't valid JSON" in result.errors[0]
    assert (home / ".claude/settings.json").read_text() == "{ nope"


def test_check_writes_nothing(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"env": {"A": "1"}})
    home = tmp_path / "home"

    result = _sync(standards, home, check=True)

    assert result.updated == [f"{home}/.claude/settings.json env.A"]
    assert not (home / ".claude").exists()
    assert not (home / ".repo-template").exists()


def test_a_file_changed_during_the_merge_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    standards = _standards(tmp_path / "s", {"env": {"A": "1"}})
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    path = home / ".claude/settings.json"
    path.write_text("{}")
    real_merge = settings_module.merge_portable

    def merge_while_claude_writes(*args: Any) -> Any:
        path.write_text('{"model": "written by Claude Code meanwhile"}')
        os.utime(path, ns=(1, 1))
        return real_merge(*args)

    monkeypatch.setattr(settings_module, "merge_portable", merge_while_claude_writes)

    result = _sync(standards, home)

    assert any("changed while globals was merging" in error for error in result.errors)
    assert "meanwhile" in path.read_text()


def test_settings_that_widen_access_are_never_distributed(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {}, {"remoteControlAtStartup": True})

    with pytest.raises(ValueError, match="widen access"):
        load_source(standards)


def test_a_link_left_dangling_by_a_pull_becomes_a_merged_file(tmp_path: Path) -> None:
    """A machine that pulls 0.4.2 before running globals: the old link's target is gone."""
    standards = _standards(tmp_path / "s", {"env": {"A": "1"}}, {"theme": "auto"})
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").symlink_to(tmp_path / "s/.claude/settings.json")

    _sync(standards, home)

    assert _settings(home) == {"env": {"A": "1"}, "theme": "auto"}


def _link_to_standards(tmp_path: Path, content: dict[str, Any]) -> Path:
    old = tmp_path / "s/.claude/settings.json"
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps(content))
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").symlink_to(old)
    return home


def test_a_link_repo_template_didnt_create_is_left_alone(tmp_path: Path) -> None:
    """A dotfiles or stow link holds the person's own settings: never merge over them."""
    dotfiles = tmp_path / "dotfiles/settings.json"
    dotfiles.parent.mkdir()
    dotfiles.write_text(json.dumps({"env": {"MINE": "1"}, "permissions": {"allow": ["Bash(ls)"]}}))
    standards = _standards(tmp_path / "s", {"env": {"A": "1"}})
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").symlink_to(dotfiles)

    result = _sync(standards, home)

    assert (home / ".claude/settings.json").is_symlink()
    assert json.loads(dotfiles.read_text())["env"] == {"MINE": "1"}
    assert "didn't create" in result.preserved[0]


def test_migration_keeps_what_was_added_through_the_link(tmp_path: Path) -> None:
    """Only what 0.4.1 distributed counts as written by repo-template."""
    home = _link_to_standards(
        tmp_path, {"enabledPlugins": {"azure@m": True, "mine@m": True}, "env": {"MINE": "1"}}
    )
    standards = _standards(
        tmp_path / "s",
        {"enabledPlugins": {"azure@m": False}},
        linked={"enabledPlugins": {"azure@m": True}},
    )

    _sync(standards, home)

    assert _settings(home) == {
        "enabledPlugins": {"azure@m": False, "mine@m": True},
        "env": {"MINE": "1"},
    }


def test_a_value_the_person_already_had_is_never_claimed(tmp_path: Path) -> None:
    """Dropping an entry from portable later must not delete the person's own equal value."""
    standards = _standards(tmp_path / "s", {"env": {"SHARED": "1"}})
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text(json.dumps({"env": {"SHARED": "1"}}))
    _sync(standards, home)
    _standards(standards, {})

    _sync(standards, home)

    assert _settings(home)["env"] == {"SHARED": "1"}


def test_a_removed_default_stays_removed(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {}, {"model": "opus"})
    home = tmp_path / "home"
    _sync(standards, home)
    (home / ".claude/settings.json").write_text("{}")

    result = _sync(standards, home)

    assert not result.needs_attention
    assert _settings(home) == {}


def test_a_hook_the_person_adds_to_a_portable_group_is_theirs(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"hooks": {"PostToolUse": [HOOK]}})
    home = tmp_path / "home"
    _sync(standards, home)
    data = _settings(home)
    mine = {"type": "command", "command": "my-logger || true"}
    data["hooks"]["PostToolUse"][0]["hooks"].append(mine)
    (home / ".claude/settings.json").write_text(json.dumps(data))
    newer = {"type": "command", "command": "receipt2 || true"}
    _standards(standards, {"hooks": {"PostToolUse": [{"matcher": "Skill", "hooks": [newer]}]}})

    result = _sync(standards, home)

    assert not result.preserved
    assert _settings(home)["hooks"] == {
        "PostToolUse": [{"matcher": "Skill", "hooks": [mine, newer]}]
    }


def test_an_existing_empty_list_doesnt_split_check_from_globals(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"permissions": {"deny": ["X"]}})
    home = tmp_path / "home"
    _sync(standards, home)
    data = _settings(home)
    data["permissions"]["ask"] = []
    (home / ".claude/settings.json").write_text(json.dumps(data))
    before = (home / ".claude/settings.json").read_text()

    assert not _sync(standards, home, check=True).needs_attention
    _sync(standards, home)
    assert (home / ".claude/settings.json").read_text() == before


def test_a_malformed_state_file_is_reported_not_a_crash(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"env": {"A": "1"}})
    home = tmp_path / "home"
    (home / ".repo-template").mkdir(parents=True)
    (home / ".repo-template/globals-state.json").write_text('{"claude_settings": {"kept": []}}')

    result = _sync(standards, home)

    assert result.errors and "delete it to reset" in result.errors[0]


def test_duplicate_portable_rules_are_written_once(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"permissions": {"deny": ["X", "X"]}})
    home = tmp_path / "home"

    _sync(standards, home)

    assert _settings(home)["permissions"]["deny"] == ["X"]


@pytest.mark.parametrize(
    ("portable", "message"),
    [
        ({"permissions": {"allow": ["Bash(ls)"]}}, "widens access"),
        (
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x"}]}]}},
            "can never block",
        ),
        ({"permissions": {"deny": ["not a rule!"]}}, "isn't a permission rule"),
        ({"enabledPlugins": {"a@m": "yes"}}, "must be a bool"),
    ],
)
def test_the_source_is_validated(tmp_path: Path, portable: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_source(_standards(tmp_path / "s", portable))


def test_the_shipped_portable_settings_are_valid_and_hooks_never_block() -> None:
    """AGENTS.md: hooks in the portable settings always exit 0."""
    portable, defaults, linked = load_source(ROOT)

    commands = [
        hook["command"]
        for groups in portable["hooks"].values()
        for group in groups
        for hook in group["hooks"]
    ]
    assert commands and all(command.endswith("|| true") for command in commands)
    assert "permissions" in linked and "remoteControlAtStartup" not in defaults


def test_a_version_1_state_file_is_converted(tmp_path: Path) -> None:
    """The first 0.4.2 build recorded the applied portable object whole."""
    standards = _standards(tmp_path / "s", {"enabledPlugins": {"a@m": False}}, {"model": "opus"})
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {"a@m": True}}))
    (home / ".repo-template").mkdir()
    v1 = {"claude_settings": {"applied": {"enabledPlugins": {"a@m": True}}, "kept": {}}}
    (home / ".repo-template/globals-state.json").write_text(json.dumps(v1))

    result = _sync(standards, home)

    assert not result.errors and not result.preserved
    assert _settings(home) == {"enabledPlugins": {"a@m": False}}  # ours, so it follows portable


LINKED = {
    "enabledPlugins": {"azure@m": True, "github@m": True},
    "permissions": {"deny": ["Read(./.env)", "Read(./**/*.key)"]},
    "hooks": {"PostToolUse": [HOOK]},
}


def test_a_dangling_link_migrates_like_a_fresh_machine(tmp_path: Path) -> None:
    """The documented upgrade (checkout, pull, globals) always leaves the link dangling: every
    portable entry must still be written, and nothing reported as removed."""
    portable = {
        "enabledPlugins": {"azure@m": False, "github@m": True},
        "permissions": {"deny": ["Read(./**/.env)", "Read(./**/*.key)"]},
        "hooks": {"PostToolUse": [HOOK]},
    }
    standards = _standards(tmp_path / "s", portable, {"model": "opus"}, linked=LINKED)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").symlink_to(tmp_path / "s/.claude/settings.json")

    result = _sync(standards, home)

    assert not result.preserved and not result.errors
    assert _settings(home) == {**portable, "model": "opus"}


@pytest.mark.parametrize(
    "state",
    [
        '{"claude_settings": [1]}',
        '{"claude_settings": "x"}',
        '{"claude_settings": {"version": 2, "defaults_written": [[1]]}}',
        '{"claude_settings": {"applied": {"enabledPlugins": []}}}',
        '{"claude_settings": {"version": 1, "applied": {"hooks": {"Stop": ["x"]}}}}',
        "{ not json",
    ],
)
def test_an_unusable_state_file_is_an_error_not_a_crash(tmp_path: Path, state: str) -> None:
    standards = _standards(tmp_path / "s", {"env": {"A": "1"}})
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text("{}")
    (home / ".repo-template").mkdir()
    (home / ".repo-template/globals-state.json").write_text(state)

    result = _sync(standards, home)

    assert len(result.errors) == 1 and "delete it to reset" in result.errors[0]
    assert _settings(home) == {}


def test_matchers_none_empty_and_star_are_one_group(tmp_path: Path) -> None:
    receipt = {"type": "command", "command": "receipt || true"}
    standards = _standards(
        tmp_path / "s", {"hooks": {"Stop": [{"matcher": "", "hooks": [receipt]}]}}
    )
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [receipt]}]}})
    )

    first = _sync(standards, home)
    second = _sync(standards, home)

    assert not first.preserved and not second.needs_attention
    assert _settings(home)["hooks"] == {"Stop": [{"hooks": [receipt]}]}


def test_an_edited_portable_hook_is_a_local_change_not_a_removal(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"hooks": {"PostToolUse": [HOOK]}})
    home = tmp_path / "home"
    _sync(standards, home)
    data = _settings(home)
    data["hooks"]["PostToolUse"][0]["hooks"][0]["timeout"] = 5
    (home / ".claude/settings.json").write_text(json.dumps(data))

    first = _sync(standards, home)
    second = _sync(standards, home)

    assert len(first.preserved) == 1 and "changed on this machine; kept" in first.preserved[0]
    assert not second.needs_attention
    assert _settings(home)["hooks"]["PostToolUse"][0]["hooks"] == [
        {"type": "command", "command": "receipt || true", "timeout": 5}
    ]


def test_a_kept_entry_is_reported_again_when_the_standard_changes(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"env": {"MODE": "a"}})
    home = tmp_path / "home"
    _sync(standards, home)
    (home / ".claude/settings.json").write_text(json.dumps({"env": {"MODE": "mine"}}))
    assert _sync(standards, home).preserved
    assert not _sync(standards, home).needs_attention
    _standards(standards, {"env": {"MODE": "b"}})

    result = _sync(standards, home)

    assert result.preserved and _settings(home)["env"] == {"MODE": "mine"}


def test_taking_the_standards_value_back_clears_the_kept_marker(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"env": {"MODE": "a"}})
    home = tmp_path / "home"
    _sync(standards, home)
    (home / ".claude/settings.json").write_text(json.dumps({"env": {"MODE": "mine"}}))
    _sync(standards, home)
    (home / ".claude/settings.json").write_text(json.dumps({"env": {"MODE": "a"}}))
    assert not _sync(standards, home).needs_attention
    (home / ".claude/settings.json").write_text(json.dumps({"env": {"MODE": "mine"}}))

    assert _sync(standards, home).preserved  # a new local change is reported again


def test_a_foreign_link_is_reported_once(tmp_path: Path) -> None:
    dotfiles = tmp_path / "dotfiles.json"
    dotfiles.write_text("{}")
    standards = _standards(tmp_path / "s", {"env": {"A": "1"}})
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").symlink_to(dotfiles)

    assert _sync(standards, home).preserved
    assert not _sync(standards, home).needs_attention
    assert not _sync(standards, home, check=True).needs_attention


def test_a_hand_replaced_link_with_the_distributed_content_is_adopted(tmp_path: Path) -> None:
    portable = {**LINKED, "permissions": {"deny": ["Read(./**/.env)", "Read(./**/*.key)"]}}
    standards = _standards(tmp_path / "s", portable, linked=LINKED)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text(json.dumps(LINKED))

    result = _sync(standards, home)

    assert not result.preserved
    assert _settings(home)["permissions"]["deny"] == ["Read(./**/*.key)", "Read(./**/.env)"]
    # (the old rule is removed in place; the new one is appended)


def test_containers_emptied_by_the_standard_are_removed(tmp_path: Path) -> None:
    standards = _standards(
        tmp_path / "s", {"permissions": {"deny": ["X"]}, "hooks": {"Stop": [HOOK]}}
    )
    home = tmp_path / "home"
    _sync(standards, home)
    _sync(standards, home)
    _standards(standards, {})

    _sync(standards, home)

    assert _settings(home) == {}


def test_an_unchanged_run_doesnt_rewrite_the_state_file(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"hooks": {"PostToolUse": [HOOK]}})
    home = tmp_path / "home"
    _sync(standards, home)
    state = home / ".repo-template/globals-state.json"
    inode = state.stat().st_ino

    _sync(standards, home)

    assert state.stat().st_ino == inode


def test_a_settings_file_that_isnt_utf8_is_an_error(tmp_path: Path) -> None:
    standards = _standards(tmp_path / "s", {"env": {"A": "1"}})
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_bytes(b"\xff\xfe{")

    result = _sync(standards, home)

    assert result.errors and "isn't valid JSON" in result.errors[0]


def test_defaults_are_limited_to_machine_preferences(tmp_path: Path) -> None:
    standards = _standards(
        tmp_path / "s", {}, {"permissions": {"defaultMode": "bypassPermissions"}}
    )

    with pytest.raises(ValueError, match="may only set"):
        load_source(standards)
