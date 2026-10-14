---
name: openwebui
description: "Open WebUI as the chat front end for your own agents (LangGraph, Deep Agents): an OpenAI-compatible endpoint with streaming, reasoning and status events, Pipes, Tools, Actions, Filters, Rich UI embeds, OpenAPI and MCP tool servers. Use when connecting an agent or tool server to Open WebUI, writing an Open WebUI plugin, or deploying Open WebUI."
---

# Open WebUI as the front end for your agents

Open WebUI changes faster than training data. Plugin code broke at 0.9.0 (the data layer went
async) and again at 0.10.0 (Native tool calling became the default), and Filters gained a
`request` hook in 0.11.2. This skill was checked against the source and docs of 0.12.0 (released
2026-10-10) and 0.11.4. Check facts against the version you run (section 1) before you write code
from memory. Section 2 picks the integration. Sections 3 and 4 cover the default build, an agent
behind an OpenAI-compatible endpoint, and sections 5 to 7 cover the other ways in. Section 8 covers
running the instance.

## 1. Look it up for the version you run

- Instance version: `curl -s http://127.0.0.1:3000/api/version` (no auth needed). Recent releases:
  `gh api repos/open-webui/open-webui/releases --jq '.[0:5][] | [.tag_name, .published_at] | @tsv'`.
- The docs are built for agents to read, so no docs MCP is needed:
  - search: `curl -s 'https://docs.openwebui.com/api/search?q=event+emitter'` returns JSON
    results with `url`, `markdown_url` and `snippet`;
  - read: add `.md` to any page URL (`https://docs.openwebui.com/features/extensibility/mcp.md`);
  - index: `https://docs.openwebui.com/llms.txt` (about 90 KB). Skip `llms-full.txt` (over 4 MB);
  - cite the canonical HTML URL, without `.md`. The docs ask for this.
- The docs track the newest release. On an older instance, or when the docs say nothing, read the
  source at your tag:
  `gh api 'repos/open-webui/open-webui/contents/backend/open_webui/utils/middleware.py?ref=v0.12.0' -H 'Accept: application/vnd.github.raw'`.

## 2. Choose the integration

| You want | Build |
| --- | --- |
| Chat with your agent, using its own tools and memory | The agent as an OpenAI-compatible model (section 3). This is the default. |
| The agent needs Open WebUI's per-request context: user valves, the user's OAuth token, attached files, a confirm or input dialog | A Pipe in front of the agent (section 5) |
| Another chat model calls your agent as one tool among several | The LangGraph `/mcp` endpoint, or an OpenAPI server (section 7) |
| A function any model can call | A Tool, or an OpenAPI server for heavy dependencies or a GPU |
| A button under a message | An Action |
| Rewrite every request or response | A Filter |
| Interactive HTML in the chat | A Rich UI embed |

Don't build on Pipelines (the separate `open-webui/pipelines` server). Its README opens with
"DO NOT USE PIPELINES!" and points to Functions, it has had no commits since August 2025, and the
Open WebUI docs no longer cover it. For heavy work, run your own service (section 3 or 7). Build
with plugins and tool servers, not a fork of the SvelteKit frontend: the project closes code PRs
that no maintainer asked for.

## 3. The agent as an OpenAI-compatible model

Serve `GET /v1/models` and `POST /v1/chat/completions`. Then add the base URL (ending in `/v1`)
and a key as an OpenAI API connection under **Settings > Admin > Connections**. A tested FastAPI
server that wraps a LangGraph or Deep Agents graph, with the matching connection settings and
Compose file, is in [references/agent-endpoint.md](references/agent-endpoint.md). The endpoint has
to get these right:

- **Rebuild the agent input from `messages` on every turn.** Each request carries the whole
  current branch of the conversation, and editing or regenerating a message starts a new branch.
  `messages` is the source of truth. A checkpoint keyed on the chat id goes stale on the first
  regenerate.
- **Stream `chat.completion.chunk` events over SSE** and end with `data: [DONE]`. Send reasoning
  in `delta.reasoning_content` (`reasoning` and `thinking` also work) or inline as
  `<think>…</think>`. Open WebUI shows it in a collapsible Thinking block.
- **Keep the agent's own tool calls out of `delta.tool_calls`.** Open WebUI treats a streamed tool
  call as a call to one of its own tools. For a tool name it didn't offer, it replies
  `Error: Tool "x" not found.` and calls the agent again (0.11.4 and 0.12.0 middleware). Report
  the agent's tool use as status events instead (section 4).
- **Answer `stream: false` too.** By default, titles, tags, follow-ups, autocomplete and
  search-query rewriting run on the chat model, as non-streaming requests. Set **External Task
  Model** (Settings > Admin > Interface > Tasks, `TASK_MODEL_EXTERNAL`) to a small plain model so
  these never reach the agent. The `{{TASK}}` header below names any that still arrive. Context
  compaction (off by default) has its own model setting, `CONTEXT_COMPACTION_MODEL`.
- **Decide what Open WebUI adds to the request.** In Native mode it puts its Builtin Tools in
  `tools`, and it can add attached files, memories and web results to the messages. If the agent
  owns retrieval and tools, turn off the **Builtin Tools** and **File Context** capabilities in
  the agent model's editor. If the agent should use them, handle `tool_calls` and
  `role: "tool"` messages the way any OpenAI client does.
- **Pass ids and identity in per-connection headers.** The connection's Headers field takes JSON
  with placeholders:
  `{"X-OpenWebUI-Chat-Id": "{{CHAT_ID}}", "X-OpenWebUI-Message-Id": "{{MESSAGE_ID}}", "X-OpenWebUI-User-Id": "{{USER_ID}}", "X-OpenWebUI-Task": "{{TASK}}"}`.
  Placeholders work from v0.9.3, and `{{TASK}}` from v0.10.0. `{{TASK}}` is empty on a chat turn
  and holds a name such as `title_generation` for background work.
  `ENABLE_FORWARD_USER_INFO_HEADERS=True` is the instance-wide alternative, with two drawbacks: it
  sends every user's name, email and role to every backend, cloud providers included, and on model
  connections it forwards the chat id but not the message id.
- **Anyone who can reach the agent can forge plain headers.** Keep the agent on the Compose network
  behind the connection key, or set `FORWARD_USER_INFO_HEADER_JWT_SECRET` (together with the
  forwarding flag) to get a signed HS256 `X-OpenWebUI-User-Jwt` header instead.

## 4. Status, citations and embeds from the agent

- **Documented route:** `POST {open-webui}/api/v1/chats/{chat_id}/messages/{message_id}/event`
  with `Authorization: Bearer <key>` and a body such as
  `{"type": "status", "data": {"description": "Searching", "done": false}}`. The key must belong to
  the chat's owner or an admin. Use a dedicated service-account admin, with API Keys turned on
  (Settings > Admin > Authentication; off by default) and `ENABLE_ADMIN_CHAT_ACCESS` left at its
  default of `True`. Get the ids from the headers above. Temporary and channel chats (ids starting
  `temporary:`, `local:` or `channel:`) aren't saved, so the route has nothing to post to.
- **That key is a full admin credential.** It can read every chat and create Functions, which run
  code on the server. Keep it in the agent's environment only. If nothing else on the instance
  uses API keys, turn on **API Key Endpoint Restrictions** (Settings > Admin > Authentication)
  and allow only `/api/v1/chats`. That applies to every API key on the instance.
- **Inline shortcut:** a stream chunk `data: {"event": {"type": "status", "data": {...}}}` goes to
  the same emitter, needs no key, and shows live in temporary chats too. It is in the source from
  v0.9.0 through v0.12.0 but not in the docs, so re-test it after every upgrade.
- **Event bodies.** Use the short names, since those are the ones saved with the message:
  - `status` `{description, done, hidden}`. Finish with `done: true`, or the last status line
    keeps its loading shimmer forever.
  - `source` for citations.
  - `embeds` `{"embeds": ["<html>…</html>" or a URL], "replace": false}` for Rich UI.
  - `notification` `{type: info|success|warning|error, content}` for a toast.
  - `files` for attachments.
- **Dialogs** (`confirmation`, `input`) need `__event_call__`, a WebSocket round trip that only
  in-process plugins get. If the agent pauses for approval (a LangGraph `interrupt`, see
  `langgraph-human-in-the-loop` in the langchain pack), put a Pipe in front of it, or ask for the
  approval as an ordinary chat turn.

## 5. A Pipe in front of the agent

A Pipe is a Function that shows up as a model. `pipe(self, body, ...)` gets reserved arguments by
name: `__user__` (its `"valves"` key holds the UserValves), `__metadata__`, `__chat_id__`,
`__message_id__`, `__files__`, `__oauth_token__`, `__event_emitter__`, `__event_call__`,
`__request__` and `__task__`. The two event helpers are `None` on plain API calls. A `pipes()`
method makes one Pipe serve several models (a "manifold").

- **Keep the agent in its own service and make the Pipe a thin async relay** (the example is in
  the reference). The Pipe runs inside Open WebUI's process: its `requirements:` frontmatter is
  pip-installed into Open WebUI at startup (`ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS`, on by
  default), and any blocking call stalls every user. Use `httpx.AsyncClient`.
- **Make `pipe` a coroutine with two return types.** Return an async generator when
  `body["stream"]` is true, and a completion dict when it is false. On the non-streaming path, a
  generator's items get joined into the reply text.
- **Send content with return or yield.** Use events for status, sources, files and embeds. If
  `message` or `replace` events are the only way content arrives, it gets overwritten.
- **Valve secrets are stored as plaintext** in the database unless `ENABLE_VALVE_ENCRYPTION=true`.
  `json_schema_extra={"input": {"type": "password"}}` only hides them in the UI.

## 6. Tools, Actions, Filters and Rich UI

A plugin is one Python file: a frontmatter docstring whose `"""` is the file's first line (`title`,
`author`, `version`, `requirements`, `required_open_webui_version`, ...), then a class named
`Tools`, `Pipe`, `Filter`, `Action` or `Event`. Plugins run arbitrary Python on the server, so
anyone allowed to create them has a shell.
Anatomy, hooks and Rich UI rules are in [references/plugins.md](references/plugins.md). Three
rules come up in almost every plugin:

- **Native is the only supported tool-calling mode, and the default since v0.10.0.** Legacy
  (formerly "Default") is unsupported. A model left unset doesn't carry the string `"native"`, so a
  plugin that branches checks
  `(__metadata__ or {}).get("params", {}).get("function_calling") == "legacy"` and treats
  everything else as Native. In Native mode, the `message`, `chat:message:delta`, `chat:message`
  and `replace` events get overwritten. `status`, `notification`, `source`/`citation`, `files`,
  `confirmation`, `input` and `chat:message:follow_ups` all work.
- **Database methods on the `open_webui.models.*` classes are coroutines since 0.9.0**
  (`await Users.get_user_by_id(...)`), and so is every helper that calls one.
- **Rich UI is a sandboxed iframe.** A Tool or Action returns
  `HTMLResponse(html, headers={"Content-Disposition": "inline"})`. `allow-scripts` and
  `allow-downloads` are always on, and same-origin access is a per-user setting that is off by
  default. An embed therefore can't reach Open WebUI's cookies or API, and it reports its height
  with `postMessage`. Design for it staying off: the docs say to turn same-origin on only for
  content you trust. A React or other web-UI build has to be one self-contained HTML document.

## 7. Tool servers: OpenAPI, MCP and the LangGraph endpoint

- **OpenAPI** is the docs' preferred path. The Open WebUI backend calls servers an admin adds
  (Settings > Admin > Integrations), so `localhost` there means Open WebUI's own container. Servers
  a user adds (Settings > Integrations, which needs the Direct Tool Servers permission) are called
  from the browser and need CORS. Global tools stay off in a chat until the user switches them on
  in the Integrations menu. To write the server, use the `fastapi-services` skill.
- **MCP** has been native since v0.6.31. It is Streamable HTTP only, and only admins can add
  servers: set Type to **MCP (Streamable HTTP)**, not OpenAPI. Leave Auth at **None** unless the
  server needs a token, because Bearer with an empty key sends a bare `Authorization: Bearer`.
  To write the server, use the `mcp-servers` skill.
- **mcpo** turns a stdio or SSE MCP server into an OpenAPI server, so add it with Type
  **OpenAPI**:
  `uvx mcpo@0.0.20 --host 127.0.0.1 --port 8001 --api-key "$MCPO_API_KEY" -- <server command>`.
  Without `--host` it binds 0.0.0.0. In Compose it needs 0.0.0.0 inside its container, so run it
  as a service with no published port. To find newer releases:
  `gh api repos/open-webui/mcpo/releases`.
- **LangGraph Agent Server** serves MCP at `/mcp` (Streamable HTTP, `langgraph-api>=0.2.3`), and
  Managed Deep Agents deployments expose the same endpoint. `langgraph dev` listens on
  127.0.0.1:2024. Each graph becomes a tool: its name is the graph's name, its description is the
  `description` in `langgraph.json`, and its arguments come from the graph's input schema. Give
  the graph small typed input and output states, because the default `MessagesState` is too
  general for a model to fill in. Requests are stateless and use the Agent Server's own auth. A
  LangSmith deployment wants an `x-api-key` header holding a LangSmith API key: put it in the
  connection's Headers field with Auth at **None**, and treat it as a secret for the whole
  workspace. In this mode an Open WebUI model is doing the chatting, and your agent's answer comes
  back as a tool result instead of streaming into the chat.
- **External tool servers report status** through the event endpoint (section 4), using the
  `X-OpenWebUI-Chat-Id` and `X-OpenWebUI-Message-Id` headers. Those headers come from the
  forwarding flag or from the server's custom headers. User-added servers get no custom headers.

## 8. Run the instance

- **Pin the image by digest**, to the newest release at least 7 days old:
  `ghcr.io/open-webui/open-webui:<release>@sha256:<digest>`. Tags exist both with and without the
  `v`. `docker buildx imagetools inspect ghcr.io/open-webui/open-webui:<release>` prints the
  digest. Never use `main` or `latest`: both follow the main branch, not a release. Data lives in
  a volume mounted at `/app/backend/data`, and the app listens on 8080.
- **Set `WEBUI_SECRET_KEY` from the environment** (`${WEBUI_SECRET_KEY:?}`). If it's unset, the
  image generates a key inside the container. Recreating the container then signs everyone out and
  breaks MCP OAuth tokens and encrypted valves.
- **Most settings are ConfigVars:** the environment value is used on first start only, and after
  that the value saved in the admin settings wins. Examples: `OPENAI_API_BASE_URLS`,
  `OPENAI_API_CONFIGS`, `TASK_MODEL_EXTERNAL`, `DEFAULT_MODEL_PARAMS`, `WEBUI_BANNERS`. Change
  them in the UI, or set `ENABLE_PERSISTENT_CONFIG=False` so the environment wins on every start.
  `ENABLE_FORWARD_USER_INFO_HEADERS` is a plain variable that's read on every start.
- **Networking:** run Open WebUI and the agent in one Compose project and address the agent by
  service name (`http://agent:8000/v1`). On Linux, the container can't reach a host process bound
  to 127.0.0.1 (as `langgraph dev` is), not even through `host.docker.internal`, and that name
  also needs `extra_hosts: ["host.docker.internal:host-gateway"]`. Publish Open WebUI on loopback
  (`127.0.0.1:3000:8080`) unless others are meant to reach it. The first account to sign up
  becomes the admin, so create it before anyone else can reach the port. For Compose structure,
  use the `docker-compose-patterns` skill.
- **Branding:** clause 4 of the Open WebUI License forbids altering, removing, obscuring or
  replacing the "Open WebUI" name, logo or other identifiers. The exceptions are a deployment with
  at most 50 end users in any rolling 30 days, written permission, or an enterprise license that
  allows it. `WEBUI_NAME` appends " (Open WebUI)" to the name you set. Banners (`WEBUI_BANNERS`)
  and interface defaults (`DEFAULT_INTERFACE_SETTINGS`) are fine. White-labeling beyond 50 users
  needs that license.

## Check before you hand it back

Run the agent on the host first (for example
`uv run uvicorn server:app --host 127.0.0.1 --port 8000`), since the Compose file publishes no
port for it:

```bash
curl -fsS -H "Authorization: Bearer $AGENT_API_KEY" http://127.0.0.1:8000/v1/models
curl -fsSN -H "Authorization: Bearer $AGENT_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"my-agent","stream":true,"messages":[{"role":"user","content":"hi"}]}' \
  http://127.0.0.1:8000/v1/chat/completions      # chunks, then data: [DONE]
curl -fsS -H "Authorization: Bearer $AGENT_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"my-agent","stream":false,"messages":[{"role":"user","content":"hi"}]}' \
  http://127.0.0.1:8000/v1/chat/completions      # one chat.completion object
curl -fsS http://127.0.0.1:3000/api/version
```

Then, in Open WebUI:

- **Verify Connection** passes on the connection.
- In a chat that uses a tool, the status line appears and stops shimmering.
- Regenerating a reply, and editing an earlier message, both get an answer to the new branch.
- The chat gets a title.

For a plugin, run it in a chat on a model that is still on the default (Native) mode.
