from contextlib import asynccontextmanager

import pytest
from agent_example.runtime import agent_runtime
from fastmcp import FastMCP
from langchain.mcp import MCPAdapter
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command


async def test_native_tool_discovery_and_structured_invocation():
    server = FastMCP("fixture")

    @server.tool
    def lookup(name: str) -> dict[str, str]:
        return {"name": name, "status": "ready"}

    async with MCPAdapter(server) as adapter:
        tools = await adapter.list_tools()
        assert [tool.name for tool in tools] == ["lookup"]
        result = await tools[0].ainvoke({"name": "sample"})
        assert "sample" in str(result) and "ready" in str(result)


@pytest.mark.parametrize("approve", [False, True])
async def test_native_discovered_writes_require_approval_and_runtime_closes(approve):
    notes, events = [], []

    @asynccontextmanager
    async def lifespan(server):
        events.append("started")
        try:
            yield {}
        finally:
            events.append("closed")

    server = FastMCP("write-fixture", lifespan=lifespan)

    @server.tool
    def write_note(text: str) -> dict[str, str]:
        notes.append(text)
        return {"saved": text}

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    model = Model(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "write_note", "args": {"text": "native"}, "id": "native-write"}
                ],
            ),
            AIMessage(content="finished"),
        ]
    )
    config = {"configurable": {"thread_id": "native"}}
    async with agent_runtime(server, model, InMemorySaver()) as graph:
        result = await graph.ainvoke({"messages": [("user", "write")]}, config)
        assert result["__interrupt__"] and notes == []
        result = await graph.ainvoke(Command(resume=approve), config)
        assert result["messages"][-1].content == "finished"
        assert notes == (["native"] if approve else [])
    assert events == ["started", "closed"]
