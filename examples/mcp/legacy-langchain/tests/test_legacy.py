from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient


async def test_legacy_stdio_tools_remain_usable():
    import sys

    client = MultiServerMCPClient(
        {
            "fixture": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(Path(__file__).with_name("server.py"))],
            }
        }
    )
    tools = await client.get_tools()
    assert [tool.name for tool in tools] == ["add"]
    assert "7" in str(await tools[0].ainvoke({"left": 3, "right": 4}))
