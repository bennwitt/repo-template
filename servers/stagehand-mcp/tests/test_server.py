"""The server end to end: a real headless Chrome, a stub OpenAI-compatible model, and a check
that this process reaches nothing but loopback. Skipped where no Chrome is installed."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from fastmcp import Client
from stagehand_mcp.llm import Endpoint
from stagehand_mcp.server import NO_MODEL, Settings, build

PAGE = b"""<!doctype html><html><head><title>Smoke</title></head><body>
<h1>Price list</h1><p id="price">4.50</p>
<button onclick="document.title = 'Clicked'">Go</button></body></html>"""
CHROME = os.environ.get("STAGEHAND_CHROME_PATH") or next(
    filter(None, map(shutil.which, ("google-chrome", "google-chrome-stable", "chromium"))), None
)
live = pytest.mark.skipif(CHROME is None, reason="no Chrome on this machine")


def _instance(schema: dict[str, Any], text: str) -> Any:
    """The smallest value a JSON schema accepts; element IDs are the page's button."""
    if "enum" in schema:
        return schema["enum"][0]
    if "anyOf" in schema:
        return _instance(schema["anyOf"][0], text)
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        required = schema.get("required", [])
        return {
            key: _instance(value, text)
            for key, value in schema.get("properties", {}).items()
            if key in required
        }
    if kind == "array":
        return []
    if kind in ("number", "integer"):
        return 4.5
    if kind == "boolean":
        return True
    if kind == "null":
        return None
    if schema.get("pattern") and "\\d+-\\d+" in schema["pattern"]:
        found = re.search(r"\[(\d+-\d+)\] button", text)
        return found.group(1) if found else "0-0"
    return "click"


class _Site(BaseHTTPRequestHandler):
    """The page under test, and a model endpoint that answers every schema."""

    calls: list[dict[str, Any]] = []

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send(self, body: bytes, kind: str) -> None:
        self.send_response(200)
        self.send_header("content-type", kind)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._send(PAGE, "text/html")

    def do_POST(self) -> None:
        request = json.loads(self.rfile.read(int(self.headers["content-length"])))
        self.calls.append(request)
        schema = request["response_format"]["json_schema"]["schema"]
        answer = _instance(schema, json.dumps(request["messages"]))
        message = {"role": "assistant", "content": json.dumps(answer)}
        self._send(json.dumps({"choices": [{"message": message}]}).encode(), "application/json")


@pytest.fixture
def site() -> Iterator[str]:
    _Site.calls = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def reached(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every host name this process looks up or address it connects to."""
    hosts: list[str] = []
    lookup, connect = socket.getaddrinfo, socket.socket.connect

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        hosts.append(str(host))
        return lookup(host, *args, **kwargs)

    def connect_to(self: socket.socket, address: Any) -> Any:
        if isinstance(address, tuple):
            hosts.append(str(address[0]))
        return connect(self, address)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", connect_to)
    return hosts


def test_settings_come_from_the_environment() -> None:
    settings = Settings.from_env(
        {
            "STAGEHAND_MODEL_BASE_URL": "http://gpu-box:8000/v1",
            "STAGEHAND_MODEL": "qwen3",
            "STAGEHAND_MODEL_TIMEOUT": "30",
            "STAGEHAND_CDP_URL": "http://chrome.internal:9222",
            "STAGEHAND_HEADED": "yes",
            "STAGEHAND_ALLOWED_DOMAINS": "example.com, intranet.local,",
        }
    )

    assert settings.endpoint == Endpoint("http://gpu-box:8000/v1", "qwen3", None, 30.0)
    assert settings.cdp_url == "http://chrome.internal:9222"
    assert settings.headed is True
    assert settings.allowed_domains == ("example.com", "intranet.local")
    assert Settings.from_env({"STAGEHAND_MODEL": "qwen3"}).endpoint is None


async def test_the_tools_and_what_they_promise() -> None:
    async with Client(build(Settings())) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    assert sorted(tools) == [
        "act", "close", "extract", "navigate", "observe", "screenshot", "snapshot",
    ]  # fmt: skip
    read_only = {name for name, tool in tools.items() if tool.annotations.read_only_hint}
    assert read_only == {"extract", "observe", "screenshot", "snapshot"}


async def test_model_tools_explain_a_missing_model_without_starting_a_browser() -> None:
    async with Client(build(Settings())) as client:
        observed = {"selector": "xpath=/html/body", "description": "x", "method": "click"}
        for tool, arguments in (
            ("observe", {}),
            ("extract", {"instruction": "x"}),
            ("act", {"instruction": "click Go"}),
            ("act", {"instruction": observed}),
        ):
            result = await client.call_tool(tool, arguments, raise_on_error=False)
            assert result.is_error
            assert NO_MODEL in result.content[0].text


@live
async def test_the_stagehand_primitives_on_a_local_browser(site: str, reached: list[str]) -> None:
    settings = Settings(endpoint=Endpoint(f"{site}/v1", "stub"), chrome_path=CHROME)
    async with Client(build(settings)) as client:
        opened = await client.call_tool("navigate", {"url": f"{site}/"})
        assert opened.data == {"url": f"{site}/", "title": "Smoke"}
        tree = (await client.call_tool("snapshot", {})).data
        assert "button: Go" in tree

        schema = {
            "type": "object",
            "properties": {"price": {"type": "number"}},
            "required": ["price"],
        }
        extracted = await client.call_tool(
            "extract", {"instruction": "the price", "schema": schema}
        )
        assert extracted.data == {"price": 4.5}

        acted = await client.call_tool("act", {"instruction": "click the Go button"})
        assert acted.data["success"] is True
        assert "RootWebArea: Clicked" in (await client.call_tool("snapshot", {})).data

        shot = await client.call_tool("screenshot", {})
        assert shot.content[0].type == "image" and shot.content[0].mime_type == "image/png"
        assert (await client.call_tool("close", {})).data == "closed"

    assert {call["model"] for call in _Site.calls} == {"stub"}
    assert not [host for host in reached if host not in {"127.0.0.1", "localhost", "::1"}]


@live
async def test_an_observed_action_replays_without_a_model_call(site: str) -> None:
    settings = Settings(endpoint=Endpoint(f"{site}/v1", "stub"), chrome_path=CHROME)
    button = {
        "selector": "xpath=/html[1]/body[1]/button[1]",
        "description": "the Go button",
        "method": "click",
        "arguments": [],
    }
    async with Client(build(settings)) as client:
        await client.call_tool("navigate", {"url": f"{site}/"})
        acted = await client.call_tool("act", {"instruction": button})
        tree = (await client.call_tool("snapshot", {})).data

    assert acted.data["success"] is True and "RootWebArea: Clicked" in tree
    assert _Site.calls == []
