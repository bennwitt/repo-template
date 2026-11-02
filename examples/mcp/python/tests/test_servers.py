from __future__ import annotations

import asyncio
import socket
import sys
import time
from contextlib import asynccontextmanager

import httpx2
import jwt
import pytest
import uvicorn
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastmcp import Client
from fastmcp.server.auth.providers.jwt import JWTVerifier
from mcp import Client as SDKClient
from mcp.shared.exceptions import MCPError
from mcp_example.sdk_server import server as sdk_server
from mcp_example.server import ORDERS, build_app, build_server


@asynccontextmanager
async def live(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
    runner = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
    task = asyncio.create_task(runner.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not runner.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{port}"
    finally:
        runner.should_exit = True
        await asyncio.wait_for(task, 10)
        sock.close()


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_official_sdk(mode):
    async with SDKClient(sdk_server, mode=mode) as client:
        assert (await client.call_tool("divide", {"a": 6, "b": 3})).structured_content == {
            "result": 2.0
        }
        assert (await client.call_tool("divide", {"a": 6, "b": 0})).is_error
        assert (await client.call_tool("divide", {"a": "bad", "b": 3})).is_error


async def check_contract(client):
    tools = {tool.name: tool for tool in await client.list_tools()}
    assert tools["order_status"].input_schema["required"] == ["order_id"]
    assert tools["order_status"].output_schema["required"] == ["id", "status"]
    assert tools["list_orders"].input_schema["properties"]["limit"]["maximum"] == 2
    assert (await client.call_tool("order_status", {"order_id": "A-1"})).structured_content[
        "status"
    ] == "shipped"
    for name, args in [
        ("order_status", {"order_id": "B-1"}),
        ("list_orders", {"limit": 99}),
        ("order_status", {}),
        ("absent", {}),
    ]:
        result = await client.call_tool(name, args, raise_on_error=False)
        assert result.is_error
    failure = await client.call_tool("backend_failure", {}, raise_on_error=False)
    assert failure.is_error and "PRIVATE_BACKEND_DETAIL" not in str(failure)


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_in_memory_contract(mode):
    server, _ = build_server()
    async with Client(server, mode=mode) as client:
        assert client.protocol_version == ("2026-07-28" if mode == "auto" else "2025-11-25")
        await check_contract(client)


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_real_stdio(mode):
    # A module entry point exercises installed src-layout code in a real subprocess.
    from fastmcp.client.transports import StdioTransport

    transport = StdioTransport(command=sys.executable, args=["-m", "mcp_example.server", "--stdio"])
    async with Client(transport, mode=mode) as client:
        await check_contract(client)


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_real_http_and_cleanup(mode):
    server, state = build_server()
    async with live(build_app(server, state)) as url:
        async with Client(url + "/mcp", mode=mode) as client:
            await check_contract(client)
        async with httpx2.AsyncClient() as http:
            assert (await http.get(url + "/health")).status_code == 200
            assert (
                await http.post(url + "/mcp", headers={"Host": "evil.example"})
            ).status_code in (400, 403, 421)
            assert (
                await http.post(url + "/mcp", headers={"Origin": "https://evil.example"})
            ).status_code in (400, 403)
    assert state["closed"]


async def test_auth_and_owner_boundaries():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    auth = JWTVerifier(
        public_key=public,
        issuer="https://issuer.example",
        audience="orders",
        required_scopes=["read"],
    )
    server, state = build_server(auth)

    def token(**changes):
        return jwt.encode(
            {
                "sub": "alice",
                "iss": "https://issuer.example",
                "aud": "orders",
                "scope": "read",
                "exp": int(time.time()) + 60,
                **changes,
            },
            key,
            algorithm="RS256",
        )

    async with live(build_app(server, state)) as url:
        async with httpx2.AsyncClient() as http:
            for bearer in [
                None,
                "invalid",
                token(aud="other"),
                token(iss="wrong"),
                token(exp=0),
                token(scope="write"),
            ]:
                headers = {"Authorization": "Bearer " + bearer} if bearer else {}
                response = await http.post(url + "/mcp", headers=headers)
                assert response.status_code in (401, 403)
        async with Client(url + "/mcp", auth=token()) as client:
            assert (await client.call_tool("order_status", {"order_id": "A-1"})).structured_content[
                "id"
            ] == "A-1"
            assert (
                await client.call_tool("order_status", {"order_id": "B-1"}, raise_on_error=False)
            ).is_error


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_timeout_cancels_work(mode):
    server, state = build_server()
    async with Client(server, mode=mode) as client:
        with pytest.raises(MCPError, match="timed out"):
            await client.call_tool("slow", {}, timeout=0.05)
        assert state["started"]
        async with asyncio.timeout(2):
            while state["running"]:
                await asyncio.sleep(0.01)
    assert not state["running"]


async def test_representative_agent_workflow_against_independent_state():
    # Deterministic tool-using agent policy: find all owned shipped orders, following pagination.
    server, _ = build_server()
    before = dict(ORDERS)
    async with Client(server) as client:
        cursor, shipped = 0, []
        while cursor is not None:
            page = (
                await client.call_tool("list_orders", {"cursor": cursor, "limit": 1})
            ).structured_content
            for order_id in page["ids"]:
                order = (
                    await client.call_tool("order_status", {"order_id": order_id})
                ).structured_content
                if order["status"] == "shipped":
                    shipped.append(order_id)
            cursor = page["next_cursor"]
    assert shipped == [
        key for key, (owner, status) in before.items() if owner == "alice" and status == "shipped"
    ]
    assert before == ORDERS
