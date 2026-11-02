"""Local MCP fixture: synthetic orders only; no external services or credentials."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from typing import Annotated, Literal, TypedDict

from fastapi import FastAPI
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.utilities.lifespan import combine_lifespans
from mcp.types import ToolAnnotations
from pydantic import Field

ORDERS = {
    "A-1": ("alice", "shipped"),
    "A-2": ("alice", "pending"),
    "A-3": ("alice", "shipped"),
    "B-1": ("bob", "pending"),
}


class OrderResult(TypedDict):
    id: str
    status: Literal["shipped", "pending"]


class OrderPage(TypedDict):
    ids: list[str]
    next_cursor: int | None


def build_server(auth=None):
    server = FastMCP("Orders", version="1.0.0", mask_error_details=True, auth=auth)
    state = {"running": False, "closed": False, "started": False}

    def owner():
        if auth is None:  # public synthetic fixture, never a production identity fallback
            return "alice"
        token = get_access_token()
        if token is None:
            raise ToolError("Authentication required")
        return token.claims.get("sub")

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def list_orders(
        cursor: Annotated[int, Field(ge=0)] = 0, limit: Annotated[int, Field(ge=1, le=2)] = 2
    ) -> OrderPage:
        """List your order IDs; follow next_cursor until it is null."""
        ids = [key for key, value in ORDERS.items() if value[0] == owner()]
        end = cursor + limit
        return {"ids": ids[cursor:end], "next_cursor": end if end < len(ids) else None}

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def order_status(order_id: str) -> OrderResult:
        """Read an owned order's status. IDs look like A-1."""
        value = ORDERS.get(order_id)
        if value is None or value[0] != owner():
            raise ToolError("Order not found")
        return {"id": order_id, "status": value[1]}

    @server.tool()
    def backend_failure() -> str:
        """Synthetic unexpected failure for redaction testing."""
        raise RuntimeError("PRIVATE_BACKEND_DETAIL")

    @server.tool()
    async def slow() -> str:
        """Synthetic cancellable work."""
        state["running"] = True
        state["started"] = True
        try:
            await asyncio.sleep(30)
            return "done"
        finally:
            state["running"] = False

    return server, state


def build_app(server, state):
    @asynccontextmanager
    async def lifespan(app):
        yield
        state["closed"] = True

    mcp_app = server.http_app(
        path="/mcp",
        stateless_http=True,
        host_origin_protection=True,
        allowed_hosts=["127.0.0.1"],
        allowed_origins=["https://fixture.example"],
    )
    app = FastAPI(lifespan=combine_lifespans(lifespan, mcp_app.lifespan))

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.mount("/", mcp_app)
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdio", action="store_true")
    args = parser.parse_args()
    server, _ = build_server()
    if args.stdio:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
