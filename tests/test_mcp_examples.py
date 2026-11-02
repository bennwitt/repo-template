"""Offline drift checks; executable fixture suites run in their own locked environments."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from repo_template.development import load_development

ROOT = Path(__file__).resolve().parents[1]


def test_fixture_direct_dependencies_match_development_baseline() -> None:
    pins = load_development(ROOT / ".agents")
    py = tomllib.loads((ROOT / "examples/mcp/python/pyproject.toml").read_text())
    lock = tomllib.loads((ROOT / "examples/mcp/python/uv.lock").read_text())
    locked = {entry["name"]: entry["version"] for entry in lock["package"]}
    npm = json.loads((ROOT / "examples/mcp/typescript/package.json").read_text())
    npm_lock = json.loads((ROOT / "examples/mcp/typescript/package-lock.json").read_text())
    for pin in pins.values():
        if pin.registry == "pypi":
            assert f"{pin.package}=={pin.version}" in py["project"]["dependencies"]
            assert locked[pin.package] == pin.version
        else:
            dependencies = npm["dependencies"] | npm["devDependencies"]
            assert dependencies[pin.package] == pin.version
            assert npm_lock["packages"]["node_modules/" + pin.package]["version"] == pin.version


def test_skills_keep_modern_and_legacy_guidance_separate() -> None:
    dev = ROOT / ".agents/packs/mcp-developer"
    assert "2026-07-28" in (dev / "references/protocol.md").read_text()
    assert "Current version: `2024-11-05`" not in (dev / "references/protocol.md").read_text()
    guide = (dev / "references/typescript-sdk.md").read_text()
    assert "serveStdio" in guide and "legacy only" in guide
    generator = (ROOT / ".agents/packs/python-mcp-server-generator/SKILL.md").read_text()
    assert "skip `uv init`" in generator
    assert "sdk_server.py" in generator
    migration = (ROOT / ".agents/packs/mcp-typescript-sdk-upgrade-to-v2/SKILL.md").read_text()
    assert "@modelcontextprotocol/codemod@2.4.0" in migration
    assert "@modelcontextprotocol/codemod@latest" not in migration
