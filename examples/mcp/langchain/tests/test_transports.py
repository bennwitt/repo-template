import asyncio
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastmcp.client.transports import StreamableHttpTransport
from langchain.mcp import MCPAdapter

FIXTURE = Path(__file__).with_name("mcp_fixture.py")


async def test_native_stdio_multiple_servers_and_errors():
    target = {
        "mcpServers": {
            name: {"command": sys.executable, "args": [str(FIXTURE)]}
            for name in ["first", "second"]
        }
    }
    async with asyncio.timeout(20), MCPAdapter(target) as adapter:
        tools = await adapter.list_tools()
        assert len(tools) == 6 and len({t.name for t in tools}) == 6
        lookup = next(t for t in tools if t.name.endswith("lookup"))
        assert "ready" in str(await lookup.ainvoke({"name": "transport"}))
        broken = next(t for t in tools if t.name.endswith("broken"))
        # Native MCP represents protocol tool errors as tool content, not transport failures.
        assert "synthetic" in str(await broken.ainvoke({}))
        slow = next(t for t in tools if t.name.endswith("slow"))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(slow.ainvoke({}), timeout=0.05)


async def test_native_http_authentication_and_connection_cleanup():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, str(FIXTURE), "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        async with httpx.AsyncClient() as client:
            async with asyncio.timeout(15):
                while True:
                    try:
                        response = await client.get(url)
                        assert response.status_code == 401
                        break
                    except httpx.ConnectError:
                        if process.poll() is not None:
                            pytest.fail("fixture server exited before readiness")
                        await asyncio.sleep(0.05)
        with pytest.raises(Exception, match="Server returned an error response"):
            async with (
                asyncio.timeout(5),
                MCPAdapter(StreamableHttpTransport(url, auth="wrong")) as adapter,
            ):
                await adapter.list_tools()
        async with (
            asyncio.timeout(10),
            MCPAdapter(StreamableHttpTransport(url, auth="fixture-only")) as adapter,
        ):
            tools = await adapter.list_tools()
            result = await next(t for t in tools if t.name == "lookup").ainvoke({"name": "http"})
            assert "http" in str(result)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
