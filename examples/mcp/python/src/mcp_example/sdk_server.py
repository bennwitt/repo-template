"""Official SDK v2 variant; usable in an existing src-layout project."""

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

server = MCPServer("Calculator", version="1.0.0")


@server.tool()
def divide(a: float, b: float) -> float:
    """Divide a by nonzero b."""
    if b == 0:
        raise ToolError("b must not be zero")
    return a / b


if __name__ == "__main__":
    server.run()
