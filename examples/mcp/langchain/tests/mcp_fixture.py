import argparse
import asyncio

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier


def server(authenticated=False):
    auth = (
        StaticTokenVerifier(
            tokens={"fixture-only": {"client_id": "fixture", "scopes": ["read"]}},
            required_scopes=["read"],
        )
        if authenticated
        else None
    )
    app = FastMCP("native-fixture", auth=auth)

    @app.tool
    def lookup(name: str) -> dict[str, str]:
        return {"name": name, "status": "ready"}

    @app.tool
    def broken() -> str:
        raise ValueError("synthetic tool failure")

    @app.tool
    async def slow() -> str:
        await asyncio.sleep(10)
        return "late"

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    app = server(authenticated=args.port is not None)
    if args.port:
        app.run(transport="http", host="127.0.0.1", port=args.port, show_banner=False)
    else:
        app.run(transport="stdio", show_banner=False)
