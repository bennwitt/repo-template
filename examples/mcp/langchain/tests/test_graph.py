import asyncio
import json

import httpx
import pytest
from agent_example.graph import build_graph
from agent_example.hosts import foundry_host, http_app
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command


class Model(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


@pytest.mark.parametrize("approve", [True, False])
async def test_write_requires_approval_and_resume_preserves_state(approve):
    notes = []

    @tool
    async def write_note(text: str) -> str:
        """Append a synthetic note."""
        notes.append(text)
        return "saved"

    model = Model(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "write_note", "args": {"text": "hello"}, "id": "call-1"}],
            ),
            AIMessage(content="finished"),
        ]
    )
    graph = build_graph(model, [write_note], InMemorySaver(), write_tools={"write_note"})
    config = {"configurable": {"thread_id": "one"}}
    initial = await graph.ainvoke({"messages": [("user", "save a note")]}, config)
    assert initial["__interrupt__"] and notes == []
    result = await graph.ainvoke(Command(resume=approve), config)
    assert notes == (["hello"] if approve else [])
    assert result["messages"][-1].content == "finished"


async def test_timeout_becomes_a_tool_error_and_duplicate_names_are_rejected():
    @tool
    async def slow() -> str:
        """Wait longer than the execution budget."""
        await asyncio.sleep(1)
        return "late"

    model = Model(
        responses=[
            AIMessage(content="", tool_calls=[{"name": "slow", "args": {}, "id": "slow-call"}]),
            AIMessage(content="handled"),
        ]
    )
    with pytest.raises(ValueError, match="unique"):
        build_graph(model, [slow, slow], InMemorySaver())
    graph = build_graph(model, [slow], InMemorySaver(), timeout=0.03)
    result = await graph.ainvoke(
        {"messages": [("user", "try")]}, {"configurable": {"thread_id": "two"}}
    )
    assert result["messages"][-2].status == "error"


@pytest.mark.parametrize("host", ["http", "responses", "invocations"])
async def test_same_graph_runs_through_each_host(host, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTSERVER_STATE_ROOT", str(tmp_path))
    model = Model(responses=[AIMessage(content="portable result")])
    graph = build_graph(model, [], InMemorySaver())
    if host == "http":
        app, path, body = http_app(graph), "/invoke", {"message": "hi", "thread_id": "host-test"}
    else:
        app = foundry_host(graph, protocol=host).app
        path = "/" + host
        body = {"input" if host == "responses" else "message": "hi", "stream": False}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        response = await client.post(path, json=body)
    assert response.status_code == 200, response.text
    assert "portable result" in response.text


async def test_durable_resume_does_not_repeat_completed_writes(tmp_path):
    notes = []

    @tool
    async def write_note(text: str) -> str:
        """Write a synthetic note."""
        notes.append(text)
        return "saved"

    first_model = Model(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "write_note", "args": {"text": text}, "id": text}
                    for text in ["one", "two"]
                ],
            )
        ]
    )
    config = {"configurable": {"thread_id": "durable"}}
    database = str(tmp_path / "checkpoints.db")
    async with AsyncSqliteSaver.from_conn_string(database) as saver:
        graph = build_graph(first_model, [write_note], saver, write_tools={"write_note"})
        assert (await graph.ainvoke({"messages": [("user", "write twice")]}, config))[
            "__interrupt__"
        ]
        assert (await graph.ainvoke(Command(resume=True), config))["__interrupt__"]
        assert notes == ["one"]
    async with AsyncSqliteSaver.from_conn_string(database) as saver:
        graph = build_graph(
            Model(responses=[AIMessage(content="done")]),
            [write_note],
            saver,
            write_tools={"write_note"},
        )
        result = await graph.ainvoke(Command(resume=True), config)
        assert result["messages"][-1].content == "done"
        assert notes == ["one", "two"]


@pytest.mark.parametrize("host", ["http", "responses", "invocations"])
async def test_host_checkpoint_continuity_and_approval_resume(host, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTSERVER_STATE_ROOT", str(tmp_path))
    notes = []

    @tool
    async def write_note(text: str) -> str:
        """Write a synthetic note."""
        notes.append(text)
        return "saved"

    model = Model(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "write_note", "args": {"text": "hosted"}, "id": "write"}],
            ),
            AIMessage(content="continued"),
        ]
    )
    saver = InMemorySaver()
    graph = build_graph(model, [write_note], saver, write_tools={"write_note"})

    async def authorize(request, thread):
        return request.headers.get("x-fixture-approval") == "yes" and thread == "approval"

    if host == "http":
        app, path = http_app(graph, authorize_approval=authorize), "/invoke"
        body = {"message": "save", "thread_id": "approval"}
    else:
        app, path = foundry_host(graph, protocol=host).app, "/" + host
        body = {"input" if host == "responses" else "message": "save", "stream": False}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        first = await client.post(path, json=body)
        assert first.status_code == 200, first.text
        assert notes == []
        # Inspect the same checkpoint store the adapter owns; wire resume IDs must match it.
        checkpoint = next(saver.list(None))
        state = await graph.aget_state(checkpoint.config)
        interrupt_id = state.tasks[0].interrupts[0].id
        if host == "http":
            path, body = "/resume", {"thread_id": "approval", "approve": True}
            denied = await client.post(path, json=body)
            assert denied.status_code == 403 and notes == []
        else:
            data = first.json()
            resume = [
                {
                    "type": "function_call_output",
                    "call_id": interrupt_id,
                    "output": json.dumps({"resume": True}),
                }
            ]
            body = {"stream": False, "input" if host == "responses" else "message": resume}
            if host == "responses":
                body["previous_response_id"] = data["id"]
            else:
                path += "?agent_session_id=" + first.headers["x-agent-session-id"]
        second = await client.post(path, json=body, headers={"x-fixture-approval": "yes"})
        assert second.status_code == 200, second.text
        assert "continued" in second.text and notes == ["hosted"]
