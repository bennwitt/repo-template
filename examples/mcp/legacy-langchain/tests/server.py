from mcp.server.fastmcp import FastMCP

server = FastMCP("legacy-fixture")


@server.tool()
def add(left: int, right: int) -> int:
    return left + right


if __name__ == "__main__":
    server.run(transport="stdio")
