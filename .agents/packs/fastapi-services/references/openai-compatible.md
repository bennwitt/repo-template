# OpenAI-compatible chat endpoint over a LangGraph graph

Tested end to end with FastAPI 0.142.4, Starlette 1.7.0, httpx2 2.13.1, LangGraph 1.2.14,
langchain-core 1.6.7, langchain 1.4.3 (`create_agent`), openai 3.26.0 and asgi-lifespan 2.1.0. Open WebUI behaviour was checked in
its source at 0.11.4 and 0.12.0. The graph is whatever the service compiles in its lifespan
(`yield {"graph": build_graph()}`); `require_api_key` is in [auth.md](auth.md).

## The router

```python
# app/chat.py
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, ToolMessage, convert_to_messages
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from app.auth import require_api_key

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])

MODEL_ID = "docs-agent"
ANSWER_NODES = {"model"}  # the node(s) whose LLM tokens are the reply; check graph.get_graph().nodes


class ChatMessage(BaseModel):
    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None = None


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    # Other OpenAI fields (temperature, tools, stream_options, ...) are ignored: extra="ignore" is the default.


def sse(body: dict[str, Any]) -> str:
    return f"data: {json.dumps(body, separators=(',', ':'))}\n\n"


async def stream_graph(
    graph: CompiledStateGraph, inputs: dict[str, Any], config: dict[str, Any], model: str
) -> AsyncIterator[str]:
    cid, created = f"chatcmpl-{uuid.uuid4().hex}", int(time.time())

    def chunk(delta: dict[str, Any] | None = None, finish: str | None = None, **extra: Any) -> str:
        choices = [] if delta is None else [{"index": 0, "delta": delta, "finish_reason": finish}]
        return sse({"id": cid, "object": "chat.completion.chunk", "created": created,
                    "model": model, "choices": choices, **extra})

    def status(description: str, done: bool) -> str:
        # Open WebUI shows this as a status line; other clients see an empty-choices chunk.
        return chunk(event={"type": "status", "data": {"description": description, "done": done}})

    yield chunk({"role": "assistant", "content": ""})
    try:
        async for part in graph.astream(inputs, config, stream_mode=["messages", "custom"], version="v2"):
            if part["type"] == "custom":  # what tools wrote with get_stream_writer()
                yield status(str(part["data"]), done=False)
                continue
            msg, meta = part["data"]
            if isinstance(msg, ToolMessage):
                yield status(f"{msg.name} finished", done=True)
            elif isinstance(msg, AIMessage) and meta.get("langgraph_node") in ANSWER_NODES:
                for call in getattr(msg, "tool_call_chunks", None) or msg.tool_calls:
                    if call.get("name"):
                        yield status(f"Calling {call['name']}", done=False)
                if msg.text:
                    yield chunk({"content": msg.text})
        yield chunk({}, finish="stop")
    except Exception:  # CancelledError is not an Exception: a disconnect still cancels the run
        log.exception("graph run failed")  # the details stay in the log, not in the chat
        yield sse({"error": {"message": "The agent failed. Try again.", "type": "server_error"}})
    yield "data: [DONE]\n\n"


@router.get("/models")
def list_models() -> dict[str, Any]:
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "example"}]}


@router.post("/chat/completions", response_model=None)
async def chat_completions(
    body: ChatRequest,
    request: Request,
    x_openwebui_chat_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse | dict[str, Any]:
    graph: CompiledStateGraph = request.state.graph
    inputs = {"messages": convert_to_messages([m.model_dump(exclude_none=True) for m in body.messages])}
    config: dict[str, Any] = {"metadata": {"chat_id": x_openwebui_chat_id}}  # for traces, not a thread_id
    if body.stream:
        return StreamingResponse(
            stream_graph(graph, inputs, config, body.model),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    result = await graph.ainvoke(inputs, config)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.model,
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": result["messages"][-1].text}}],
    }
```

Mount it with `app.include_router(chat.router)` and point the Open WebUI connection at
`http://<host>:8000/v1`, with the service's API key.

## What it sends

A run whose model calls one tool, from the tests below (ids shortened, repeated fields elided as
`...`). The fake model returns whole messages, so the answer is one content chunk; a streaming
model sends one per token:

```text
data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1791961205,"model":"docs-agent","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}
data: {"id":"chatcmpl-1",...,"choices":[],"event":{"type":"status","data":{"description":"Calling search_docs","done":false}}}
data: {"id":"chatcmpl-1",...,"choices":[],"event":{"type":"status","data":{"description":"Searching the docs","done":false}}}
data: {"id":"chatcmpl-1",...,"choices":[],"event":{"type":"status","data":{"description":"search_docs finished","done":true}}}
data: {"id":"chatcmpl-1",...,"choices":[{"index":0,"delta":{"content":"final answer"},"finish_reason":null}]}
data: {"id":"chatcmpl-1",...,"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

Each event is followed by a blank line on the wire.

## Adapting it

- **Answer nodes.** `ANSWER_NODES` names the node(s) whose tokens form the reply. For a hand-built
  graph, read `graph.get_graph().nodes`. Every other node's LLM output (routing, grading,
  summarising) is dropped here; alternatively give those models the `nostream` tag.
- **Tool status wording.** `Calling <tool>` comes from the model's tool-call chunks, `<tool>
  finished` from the ToolMessage the tools node returns, and anything in between from
  `get_stream_writer()` inside the tool. Map tool names to friendlier text here if needed.
- **Reasoning.** Open WebUI also reads `delta.reasoning_content` (or `reasoning` or `thinking`) and
  renders it as a collapsible reasoning block. That is the place for a reasoning model's thinking,
  not `content`.
- **Usage.** To report token usage, send one more chunk before `[DONE]` with `"choices": []` and
  `"usage": {"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...}`. Open WebUI
  reads `usage` from any chunk, and the openai SDK models it as the last chunk's `usage`.
- **Client tools.** With native function calling (Open WebUI's default), Open WebUI adds the tools
  enabled in the chat to the request as `tools`. This endpoint ignores them, because the graph
  owns tool calling. To run those tools
  client-side instead, you would have to return `tool_calls` with
  `"finish_reason": "tool_calls"` and accept `role: "tool"` messages on the next request: a
  different design.
- **Stateful threads.** If the graph needs a checkpointer (interrupts, long-running memory), send
  it only the newest user message and pass `{"configurable": {"thread_id": chat_id}}`. Expect
  edits and regenerations in Open WebUI to diverge from the stored thread.

## Tests

```python
import json
from collections.abc import Iterator

import httpx2
import openai
import pytest
from asgi_lifespan import LifespanManager
from fastapi.testclient import TestClient

from app.main import app

AUTH = {"Authorization": "Bearer test-key"}
CHAT = {"model": "docs-agent", "messages": [{"role": "user", "content": "hi"}]}


def test_stream(client: TestClient) -> None:
    with client.stream("POST", "/v1/chat/completions", json=CHAT | {"stream": True}, headers=AUTH) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        events = [line.removeprefix("data: ") for line in r.iter_lines() if line.startswith("data: ")]
    assert events[-1] == "[DONE]"
    chunks = [json.loads(e) for e in events[:-1]]
    assert not [c["error"] for c in chunks if "error" in c]
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks if c["choices"])
    assert text  # or the exact reply from a fake model
    statuses = [c["event"]["data"] for c in chunks if "event" in c]
    assert not statuses or statuses[-1]["done"] is True


def test_not_streaming(client: TestClient) -> None:
    r = client.post("/v1/chat/completions", json=CHAT, headers=AUTH)
    assert r.json()["choices"][0]["message"]["role"] == "assistant"


@pytest.mark.anyio
async def test_openai_sdk() -> None:
    async with LifespanManager(app) as manager:
        transport = httpx2.ASGITransport(app=manager.app)  # manager.app carries the lifespan state
        async with httpx2.AsyncClient(transport=transport, base_url="http://test") as http:
            sdk = openai.AsyncOpenAI(api_key="test-key", base_url="http://test/v1", http_client=http)
            stream = await sdk.chat.completions.create(**CHAT, stream=True)
            text = "".join([chunk.choices[0].delta.content or "" async for chunk in stream if chunk.choices])
    assert text
```

`client`, `settings` (autouse, with `api_key="test-key"`) and `anyio_backend` are the fixtures from
SKILL.md. The SDK test is the one that catches wire-format mistakes: a missing `[DONE]`, a
malformed chunk, or a non-JSON `data:` line. Keep the tests off real models: build the graph
with a fake from `langchain_core.language_models.fake_chat_models`. Neither fake has
`bind_tools`, which `create_agent`'s model node calls on every run when the agent has tools (a
`NotImplementedError`), so subclass one and return `self`:

```python
class FakeAgentModel(FakeMessagesListChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeAgentModel":
        return self


model = FakeAgentModel(responses=[
    AIMessage("", tool_calls=[{"name": "search_docs", "args": {"q": "setup"}, "id": "call_1"}]),
    AIMessage("final answer"),
])
```

Use `FakeMessagesListChatModel` for runs with tool calls: LangGraph passes each reply on as one
whole message. `GenericFakeChatModel` streams text token by token, even when the node calls
`.invoke()`, but it streams no tool calls. A reply that only calls a tool then fails with
`No generations found in stream`, so keep it for text-only graphs.
