# Testing an MCP server

The code below passes as written with fastmcp 4.0.11, fastapi 0.142.4, pytest 9.1.1 and
pytest-asyncio 1.4.0, and the `src` side passes `mypy --strict`. It assumes a `src/<package>/`
layout; the examples call the package `demo`.

## Setup

```bash
uv add --dev "pytest==9.1.1" "pytest-asyncio==1.4.0"
```

Those were the newest releases at least 7 days old on 2026-10-14; check PyPI for newer ones.

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"   # no @pytest.mark.asyncio on every test
```

## The server and the app under test

```python
# src/demo/server.py
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

mcp = FastMCP("Orders", mask_error_details=True)

ORDERS = {"A-1": "shipped", "A-2": "pending"}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def order_status(order_id: str) -> str:
    """Return the shipping status of one order, by its id (for example A-1)."""
    if order_id not in ORDERS:
        raise ToolError(f"No order {order_id}. Ids look like A-1.")
    return ORDERS[order_id]
```

```python
# src/demo/app.py
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastmcp.utilities.lifespan import combine_lifespans

from demo.server import mcp


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield  # open and close your own clients here


mcp_app = mcp.http_app(path="/mcp", host_origin_protection="auto")
app = FastAPI(lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.mount("/", mcp_app)  # last: a mount at "/" swallows every route added after it
```

## Tests on both eras

```python
# tests/test_server.py
from collections.abc import AsyncIterator

import httpx2
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.utilities.asgi_transport import StreamingASGITransport

from demo.app import app
from demo.server import mcp


@pytest.fixture(params=["auto", "legacy"])
async def client(request: pytest.FixtureRequest) -> AsyncIterator[Client]:
    async with Client(mcp, mode=request.param) as c:
        yield c


async def test_eras(client: Client) -> None:
    assert client.protocol_version in {"2026-07-28", "2025-11-25"}


async def test_status(client: Client) -> None:
    result = await client.call_tool("order_status", {"order_id": "A-1"})
    assert result.data == "shipped"


async def test_unknown_order_is_a_readable_error(client: Client) -> None:
    result = await client.call_tool("order_status", {"order_id": "Z-9"}, raise_on_error=False)
    assert result.is_error
    assert "Ids look like A-1" in result.content[0].text


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_mounted_app(mode: str) -> None:
    def factory(**kwargs: object) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=StreamingASGITransport(app), **kwargs)

    async with app.router.lifespan_context(app):
        transport = StreamableHttpTransport("http://127.0.0.1/mcp", httpx_client_factory=factory)
        async with Client(transport, mode=mode) as c:
            assert (await c.call_tool("order_status", {"order_id": "A-2"})).data == "pending"
```

What each piece is for:

- `Client(mcp)` talks to the server object in process. `mode="auto"` lands on 2026-07-28 and
  `mode="legacy"` on 2025-11-25, so the parametrized fixture runs every test once per era.
- `call_tool` raises `ToolError` when the tool reports an error. Pass `raise_on_error=False` to
  assert on the error text the model would read. With `mask_error_details=True`, an exception
  other than `ToolError` arrives as "Error calling tool '<name>'" and nothing more; assert that
  too when the tool touches anything private.
- `test_mounted_app` proves the FastAPI wiring: the lifespan, the mount path and both eras over
  real Streamable HTTP, with no port. `StreamingASGITransport` streams each response chunk as it
  is sent; `httpx2.ASGITransport` buffers the whole response, which deadlocks any call where the
  server sends a request back mid-response.
- The lifespan is entered inside the test body with `app.router.lifespan_context(app)`, so one
  task enters and exits it. FastMCP's `run_asgi_lifespan(app)` works for an app whose lifespan
  is `mcp_app.lifespan` alone, but with `combine_lifespans` it fails with
  `RuntimeError: The server does not support "state" in the lifespan scope.`

## A tool that elicits on handshake connections

Give the legacy client a handler and assert the tool's error on the modern era:

```python
async def accept(message, response_type, params, context):
    return True

async with Client(mcp, mode="legacy", elicitation_handler=accept) as c:
    ...
```

## The official SDK's `MCPServer`

Same idea, different fixture: `from mcp import Client`, then
`async with Client(server, raise_exceptions=True) as c:`. `raise_exceptions=True` shows the real
message of a failure outside a tool body instead of the sanitized "Internal server error"; drop
it on a `mode="legacy"` client, where it re-raises inside the server task instead of the test.
The SDK's own docs use `@pytest.mark.anyio` with an `anyio_backend` fixture returning
`"asyncio"`: <https://py.sdk.modelcontextprotocol.io/v2/get-started/testing/>.
