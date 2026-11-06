"""Native MCP connections stay alive for the graph's complete hosting lifespan."""

from contextlib import asynccontextmanager

from langchain.mcp import MCPAdapter

from agent_example.graph import build_graph


@asynccontextmanager
async def agent_runtime(target, model, checkpointer, *, read_tools=frozenset()):
    async with MCPAdapter(target) as adapter:
        tools = await adapter.list_tools()
        # Unknown tools require approval; server annotations are not an authorization policy.
        yield build_graph(
            model, tools, checkpointer, write_tools={tool.name for tool in tools} - set(read_tools)
        )
