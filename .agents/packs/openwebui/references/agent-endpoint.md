# Agent endpoint for Open WebUI: tested reference

This reference has three pieces:

- an OpenAI-compatible FastAPI server around a LangGraph graph;
- the Open WebUI connection settings for it;
- an optional Pipe that relays to the server.

The server and Pipe were exercised against a fake tool-calling model with `langgraph==1.2.14`,
`langchain==1.4.3`, `langchain-core==1.6.7`, `deepagents==0.7.23`, `fastapi==0.142.4` and
`httpx==0.28.1`. Those were the newest releases at least 7 days old on 2026-10-14. To find newer
ones, check `https://pypi.org/pypi/<package>/json` or run `uv lock --upgrade-package <package>`,
then keep the 7-day cooldown. For SSE and FastAPI patterns, see the `fastapi` skill, and for tests
and auth around this server, `fastapi-services`. For the graph itself, see `langgraph-fundamentals`
or `deep-agents-core` (langchain pack).

## Server

`my_agent.agent` is any compiled graph whose model node is named `model`. Both
`langchain.agents.create_agent` and `deepagents.create_deep_agent` produce one; in a Deep Agent,
subagents run through the `task` tool. Build the graph once, at import.

```python
import json
import os
import secrets
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage

from my_agent import agent  # create_agent(...) or create_deep_agent(...), built once

MODEL_ID = "my-agent"
API_KEY = os.environ["AGENT_API_KEY"]  # the key you enter on the Open WebUI connection; required
app = FastAPI()


def check_key(request: Request) -> None:
    sent = request.headers.get("authorization", "").removeprefix("Bearer ")
    if not secrets.compare_digest(sent.encode(), API_KEY.encode()):
        raise HTTPException(status_code=401)


@app.get("/v1/models")
async def models(request: Request):
    check_key(request)
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "me"}]}


def to_messages(raw: list[dict]) -> list:
    """Open WebUI sends the whole current branch every turn: rebuild the agent input from it."""
    kinds = {"user": HumanMessage, "assistant": AIMessage, "system": SystemMessage}
    out = []
    for m in raw:
        content = m.get("content") or ""
        if isinstance(content, list):  # multimodal parts: keep the text
            content = "".join(p.get("text", "") for p in content if p.get("type") == "text")
        if m["role"] in kinds:
            out.append(kinds[m["role"]](content))
    return out


def sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def chunk(cid: str, delta: dict, finish: str | None = None) -> str:
    return sse({"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": MODEL_ID,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]})


def status(description: str, done: bool) -> str:
    # Open WebUI 0.9.0-0.12.0 hands a top-level "event" in a stream chunk to the message's
    # event emitter (backend/open_webui/utils/middleware.py). Undocumented: re-check on upgrade,
    # or post to the documented event endpoint instead (post_event below).
    return sse({"event": {"type": "status", "data": {"description": description, "done": done}}})


async def stream(inputs: dict, cid: str):
    yield chunk(cid, {"role": "assistant", "content": ""})
    async for mode, data in agent.astream(inputs, stream_mode=["messages", "updates"]):
        if mode == "messages":
            msg, meta = data
            if isinstance(msg, AIMessageChunk) and meta.get("langgraph_node") == "model":
                for block in msg.content_blocks:  # text, reasoning, tool_call_chunk, ...
                    if block["type"] == "text" and block.get("text"):
                        yield chunk(cid, {"content": block["text"]})
                    elif block["type"] == "reasoning" and block.get("reasoning"):
                        yield chunk(cid, {"reasoning_content": block["reasoning"]})
        else:  # "updates": one entry per node that finished
            for update in data.values():
                if not isinstance(update, dict):
                    continue
                for m in update.get("messages", []):
                    for call in getattr(m, "tool_calls", None) or []:
                        yield status(f"Running {call['name']}", False)
                    if isinstance(m, ToolMessage):
                        yield status(f"Finished {m.name}", True)
    yield chunk(cid, {}, "stop")
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    check_key(request)
    body = await request.json()
    task = request.headers.get("x-openwebui-task", "")  # from a {{TASK}} custom header; "" on a chat turn
    inputs = {"messages": to_messages(body["messages"])}
    cid = f"chatcmpl-{uuid.uuid4().hex}"
    if task or not body.get("stream"):
        # Titles, tags and follow-ups arrive here, non-streaming, unless a Task Model is set.
        result = await agent.ainvoke(inputs)
        return JSONResponse({"id": cid, "object": "chat.completion", "created": int(time.time()), "model": MODEL_ID,
                             "choices": [{"index": 0, "finish_reason": "stop",
                                          "message": {"role": "assistant", "content": result["messages"][-1].text}}]})
    return StreamingResponse(stream(inputs, cid), media_type="text/event-stream")
```

What the code relies on, as tested:

- A list `stream_mode` makes `astream` yield `(mode, data)` pairs.
- `"messages"` mode yields `(chunk, metadata)` pairs, and `metadata["langgraph_node"]` tells the
  model node's tokens apart from other nodes' output.
- `content_blocks` (langchain-core 1.x) turns provider reasoning into `{"type": "reasoning"}`
  blocks. That covers `additional_kwargs["reasoning_content"]` as well as reasoning sent as
  content blocks.
- Without `subgraphs=True`, `"messages"` mode skips nested graphs, so a Deep Agent's subagent
  tokens (inside the `task` tool) don't leak into the reply. Only its status lines show.
- Tool calls go out as status lines only, never as `delta.tool_calls` (see SKILL.md, section 3).
- The key is required: the server refuses to start without `AGENT_API_KEY` rather than run open.

On the task branch, the code still runs the whole graph just to write a title. Setting an External
Task Model is the cheaper fix. If background tasks must reach the server anyway, answer them with
one plain model call instead of the graph.

### The documented status route

Use this instead of the inline `status()` chunks when you want only documented behavior. It is the
same endpoint external OpenAPI and MCP tools use.

```python
import logging
import os

import httpx

OPENWEBUI_URL = os.environ["OPENWEBUI_URL"]          # e.g. http://open-webui:8080 on the Compose network
OPENWEBUI_KEY = os.environ["OPENWEBUI_API_KEY"]      # a service-account admin's API key
UNSAVED = ("temporary:", "local:", "channel:")       # chat id prefixes Open WebUI never saves


async def post_event(chat_id: str, message_id: str, event: dict) -> None:
    if not (chat_id and message_id) or chat_id.startswith(UNSAVED):
        return  # plain API calls, temporary chats and channels have nothing to post to
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{OPENWEBUI_URL}/api/v1/chats/{chat_id}/messages/{message_id}/event",
                                  headers={"Authorization": f"Bearer {OPENWEBUI_KEY}"}, json=event)
            r.raise_for_status()
    except httpx.HTTPError as e:  # a lost status line must never break the answer
        logging.getLogger(__name__).warning("event post failed: %s", e)
```

Read the ids from the `X-OpenWebUI-Chat-Id` and `X-OpenWebUI-Message-Id` request headers that the
connection's custom headers set. To attach a Rich UI embed, post
`{"type": "embeds", "data": {"embeds": [html]}}` the same way.

## Connection settings

Set these on a new OpenAI API connection in **Settings > Admin > Connections**:

| Field | Value |
| --- | --- |
| URL | `http://agent:8000/v1`: the Compose service name, as the Open WebUI backend sees it |
| API Key | the value of `AGENT_API_KEY` |
| Model IDs | leave empty, since `/v1/models` lists the agent; fill it in only for a server without `/models` |
| Headers | `{"X-OpenWebUI-Chat-Id": "{{CHAT_ID}}", "X-OpenWebUI-Message-Id": "{{MESSAGE_ID}}", "X-OpenWebUI-User-Id": "{{USER_ID}}", "X-OpenWebUI-Task": "{{TASK}}"}` |
| Provider (Advanced) | Default |

Then:

- Click **Verify Connection**. It calls `/models` with the key.
- In the agent model's editor, decide on **Builtin Tools** and file context (SKILL.md, section 3).
- Set **External Task Model** (Settings > Admin > Interface > Tasks) to a small plain model on
  another connection.

## Compose

`docker compose config -q` accepts this file. It never started a container.

```yaml
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:<release>@sha256:<digest>
    ports: ["127.0.0.1:3000:8080"]
    environment:
      WEBUI_SECRET_KEY: ${WEBUI_SECRET_KEY:?set WEBUI_SECRET_KEY}
      # Seeds the connection on the first start only (ConfigVars); edit it in the UI afterwards.
      OPENAI_API_BASE_URLS: http://agent:8000/v1
      OPENAI_API_KEYS: ${AGENT_API_KEY:?set AGENT_API_KEY}
      OPENAI_API_CONFIGS: >-
        {"0": {"enable": true, "headers": {"X-OpenWebUI-Chat-Id": "{{CHAT_ID}}",
        "X-OpenWebUI-Message-Id": "{{MESSAGE_ID}}", "X-OpenWebUI-User-Id": "{{USER_ID}}",
        "X-OpenWebUI-Task": "{{TASK}}"}}}
    volumes:
      - open-webui:/app/backend/data
    depends_on: [agent]
  agent:
    build: .
    command: ["uv", "run", "--no-sync", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
    environment:
      AGENT_API_KEY: ${AGENT_API_KEY:?set AGENT_API_KEY}
    # No ports: Open WebUI reaches it as http://agent:8000/v1 on the Compose network.

volumes:
  open-webui: {}
```

- The agent listens on 0.0.0.0 inside its container, so the Open WebUI container can reach it,
  and no port is published on the host.
- Both keys come from the shell or from a `.env` file that git ignores. Generate them with
  `openssl rand -hex 32`.
- `<release>` is the newest Open WebUI release at least 7 days old
  (`gh api repos/open-webui/open-webui/releases`), and the digest comes from
  `docker buildx imagetools inspect`.
- For the agent's image, see the `docker-build-strategies` and `uv` skills.

## Optional: a Pipe that relays to the server

Use this when the agent needs Open WebUI's per-request context. The Pipe forwards the stream
untouched, so the agent's inline status events still reach the chat. Add more of the reserved
arguments (`__oauth_token__`, `__files__`, `__event_call__`) as the agent needs them.

```python
"""
title: My Agent
description: Chat with my agent, passing Open WebUI user context.
version: 0.1.0
"""

import httpx
from pydantic import BaseModel, Field


class Pipe:
    class Valves(BaseModel):
        AGENT_URL: str = Field("http://agent:8000/v1", description="Reachable from the Open WebUI backend")
        AGENT_MODEL: str = Field("my-agent")
        AGENT_API_KEY: str = Field("", json_schema_extra={"input": {"type": "password"}})

    def __init__(self):
        self.valves = self.Valves()

    async def pipe(self, body: dict, __user__: dict, __metadata__: dict):
        payload = {**body, "model": self.valves.AGENT_MODEL}
        headers = {  # the same names the connection's custom headers send, so the server needn't care
            "Authorization": f"Bearer {self.valves.AGENT_API_KEY}",
            "X-OpenWebUI-User-Id": __user__["id"],
            "X-OpenWebUI-Chat-Id": __metadata__.get("chat_id") or "",
            "X-OpenWebUI-Message-Id": __metadata__.get("message_id") or "",
            "X-OpenWebUI-Task": str(__metadata__.get("task") or ""),
        }
        if not body.get("stream"):
            async with httpx.AsyncClient(base_url=self.valves.AGENT_URL, timeout=300) as client:
                r = await client.post("/chat/completions", json=payload, headers=headers)
                r.raise_for_status()
                return r.json()
        return self._relay(payload, headers)

    async def _relay(self, payload: dict, headers: dict):
        async with httpx.AsyncClient(base_url=self.valves.AGENT_URL, timeout=None) as client:
            async with client.stream("POST", "/chat/completions", json=payload, headers=headers) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if line.startswith("data:") and line.strip() != "data: [DONE]":
                        yield line  # Open WebUI adds the blank line, the stop chunk and [DONE]
```

What the code relies on, from `backend/open_webui/functions.py` at v0.11.4 and v0.12.0:

- `pipe` is a coroutine, so Open WebUI awaits it.
- It streams any async generator that `pipe` returns, line by line.
- A yielded line that starts with `data:` passes through unchanged, with `\n\n` added.
- Open WebUI sends its own stop chunk and `data: [DONE]` after the generator ends.
- A dict returned on the non-streaming path is sent as is.
