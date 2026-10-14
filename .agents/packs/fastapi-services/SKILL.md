---
name: fastapi-services
description: "FastAPI services: tests that run the lifespan (httpx2, TestClient, anyio), PyJWT, pwdlib and Entra ID auth, CORS, Open WebUI OpenAPI tool servers with stable operationIds, an OpenAI-compatible SSE chat endpoint over a LangGraph graph. Use when testing or securing a FastAPI service, or serving one to Open WebUI or OpenAI clients."
---

# FastAPI services

The `fastapi` skill covers FastAPI's own conventions: Annotated dependencies, return types,
routers and the `fastapi.sse` basics. This skill covers what a service built on it adds: tests
that run the real lifespan, auth, CORS, Open WebUI tool servers, and an OpenAI-compatible chat
endpoint in front of a LangGraph graph. Mounting an MCP server into the app is the `mcp-servers`
skill's job. Open WebUI's side (connection settings, task model, the event endpoint, plugins) is
the `openwebui` skill's.

## 1. Read the lock first

Read `uv.lock` for `fastapi`, `starlette`, `httpx`, `httpx2` and `langgraph`. Their versions
decide which of the rules below apply:

| Behaviour | Since |
|---|---|
| `HTTPBearer` and the other security classes answer missing credentials with 401, not 403 | FastAPI 0.122.0 |
| JSON bodies need a JSON `Content-Type` (`strict_content_type`, on by default) | FastAPI 0.132.0 |
| `fastapi.sse` (`EventSourceResponse`, `ServerSentEvent`) | FastAPI 0.135.0 |
| `TestClient` uses `httpx2`, and warns when it falls back to `httpx` | Starlette 1.2.0 |
| `graph.astream(..., version="v2")` typed stream parts | LangGraph 1.1 |

When adding or upgrading a package, pin the newest release that is at least 7 days old. This
lists recent releases with their upload dates:

```bash
curl -s https://pypi.org/pypi/fastapi/json | jq -r '.releases | to_entries[] | select(.value | length > 0) | "\(.value[0].upload_time) \(.key)"' | sort | tail -5
```

## 2. Lifespan and settings

Build anything expensive or networked in `lifespan`, such as the compiled graph and HTTP clients.
Then importing the app (for a test, or for `fastapi dev`) has no side effects. Yield a dict and
read the values as `request.state.<key>`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, Any]]:
    async with httpx2.AsyncClient(timeout=30) as http:
        yield {"graph": build_graph(), "http": http}

app = FastAPI(lifespan=lifespan, generate_unique_id_function=operation_id)  # see section 6
```

- `lifespan=` replaces `@app.on_event`. Once `lifespan` is set, `startup` and `shutdown`
  handlers stop running, so convert every one of them.
- Only the main app's lifespan runs. A mounted sub-app's lifespan has to be entered from yours.
- Settings come from `pydantic-settings` through a cached dependency that tests override (the
  class is in [references/auth.md](references/auth.md)). Secrets are `SecretStr` fields without
  real defaults, in a git-ignored `.env`. A `list[str]` field reads JSON
  (`APP_CORS_ORIGINS='["https://chat.example.com"]'`); a comma-separated value raises `SettingsError`.
- For outbound HTTP, new code can use `httpx2`, Pydantic's continuation of HTTPX (openai 3.26.0
  already depends on it).
- `fastapi dev` listens on 127.0.0.1, but `fastapi run` on 0.0.0.0. Outside a container, pass
  `--host 127.0.0.1` unless the service is meant to be reachable from the network.

## 3. Tests

Add `pytest` and `httpx2` as dev dependencies, pinned as in section 1, whatever FastAPI's testing
tutorial says (`uv add httpx`, checked at 0.142.4). `TestClient` imports `httpx2` first. With only
`httpx`, which `fastapi[standard]` still pulls in, it emits `StarletteDeprecationWarning` (a
`UserWarning`), and under `filterwarnings = ["error"]` pytest fails to collect the module.

```python
@pytest.fixture(autouse=True)
def settings() -> Iterator[Settings]:
    test_settings = Settings(_env_file=None, api_key=SecretStr("test-key"))  # ignore the real .env
    app.dependency_overrides[get_settings] = lambda: test_settings
    yield test_settings
    app.dependency_overrides.clear()

@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as client:  # `with` runs the lifespan
        yield client

@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
```

- `TestClient(app)` without `with` skips the lifespan. The first handler that reads
  `request.state.graph` then fails with `AttributeError: 'State' object has no attribute 'graph'`.
- `dependency_overrides` reaches dependencies only. Code that calls `get_settings()` itself, such
  as the lifespan or middleware arguments, reads the real environment.
- For async tests use `@pytest.mark.anyio`; the plugin ships with anyio, which Starlette already
  depends on. anyio 4.12+ runs each test once per importable backend, so pin `anyio_backend` as
  above. Use one async test plugin per repository: if the repository already uses
  pytest-asyncio, keep it.
- Build an async client as `httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test")`.
  `AsyncClient` has no `app=` argument. `ASGITransport` does not run the lifespan either: wrap the
  app in `asgi_lifespan.LifespanManager(app)` (the `asgi-lifespan` package, a dev dependency) and
  pass `manager.app`, which carries the lifespan state, to the transport.
- Read a stream with `client.stream(...)` and `r.iter_lines()`. Tests for the chat endpoint,
  including one through the `openai` SDK, are in [references/openai-compatible.md](references/openai-compatible.md).

## 4. Auth

Pick the pattern by who issues the token. Code for each is in [references/auth.md](references/auth.md).

- **The service issues its own tokens** (a username and password login): follow FastAPI's OAuth2
  JWT tutorial, which uses PyJWT and `pwdlib[argon2]` (`PasswordHash.recommended()` is
  Argon2id). Keep its dummy-hash check for unknown usernames. Two changes: read the signing key
  from settings (the tutorial hard-codes one), and make the login path operation a plain `def`,
  because the tutorial's `async def` login runs CPU-bound Argon2 on the event loop.
- **An identity provider issues the tokens** (Entra ID, any OIDC provider): install
  `pyjwt[crypto]` for RS256. Reuse one `jwt.PyJWKClient` per JWKS URL (it caches the key set,
  300 s by default). It fetches with blocking `urllib`, so the dependency that uses it is a
  plain `def`. Always pass `audience` and `issuer`: a token with an `aud` fails with
  `InvalidAudienceError` when you pass none. Entra ID's values depend on the token version.
- **Open WebUI calls the service** (an OpenAI-compatible connection or a global tool server):
  check the connection's static key with `HTTPBearer` and `secrets.compare_digest` on bytes (a
  non-ASCII `str` raises `TypeError`). To learn which user is behind a call, set
  `ENABLE_FORWARD_USER_INFO_HEADERS=true` and `FORWARD_USER_INFO_HEADER_JWT_SECRET` on Open WebUI.
  Its backend then sends an HS256 JWT in `X-OpenWebUI-User-Jwt`, with claims `sub`, `email`,
  `name`, `role`, `iss: "open-webui"` and a 300 s default expiry (source, 0.11.4 and 0.12.0).
  Without the secret it sends plain `X-OpenWebUI-User-*` headers that any caller can forge. The
  flag is instance-wide: every model connection and tool server, cloud providers included, gets
  each user's name, email and role.
- **Wherever PyJWT verifies tokens, require 2.15.0 or later.** 2.13.0, 2.14.0 and 2.15.0 each
  fixed advisories, including forgery through key confusion and a crash in
  `get_signing_key_from_jwt` on a crafted token.

## 5. CORS

- Add `CORSMiddleware` only when a browser calls the service directly. Open WebUI's user tool
  servers (Settings, then Integrations) are called from the browser and need it. Global tool
  servers (Admin Settings) and OpenAI-compatible connections are called by Open WebUI's backend,
  where CORS never applies.
- List the allowed origins exactly, from settings. With `allow_origins=["*"]` and
  `allow_credentials=True`, Starlette (checked at 1.7.0) echoes any request's `Origin` with
  `Access-Control-Allow-Credentials: true`, so every website can make credentialed calls. Open
  WebUI's FAQ example uses that pair; list the Open WebUI origin instead.
- `allow_credentials` covers cookies, TLS client certificates and browser-managed HTTP auth. A
  bearer token the page puts in `Authorization` doesn't need it, but `Authorization` has to be in
  `allow_headers`, or Starlette rejects the preflight with 400.
- Leave `strict_content_type` on. It blocks the cross-site `fetch()` that skips the CORS
  preflight to reach an unauthenticated API on localhost. A consequence: `curl -d` sends a form
  content type and gets a 422, so add `-H 'Content-Type: application/json'`.

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
```

## 6. Open WebUI OpenAPI tool servers

Open WebUI fetches `<url>/openapi.json` (the default path) and turns each operation into a tool.
The rules below come from its source, which is the same in 0.11.4 and 0.12.0:

- The tool name is the `operationId`, and operations without one are skipped. FastAPI's generated
  IDs (`read_item_api_v1_items__item_id__get`) are long, and they change whenever a path or prefix
  changes, which renames the tool. Use the function name, and give functions distinctive names
  (`search_docs`, not `search`): Open WebUI prefixes the server ID on a clash across servers, and
  admins filter tools by name.

```python
def operation_id(route: APIRoute) -> str:
    return route.name
```

- Model tool names must match `^[a-zA-Z0-9_-]{1,64}$` (OpenAI's limit), and FastAPI only warns
  about a duplicate ID. Check both in a test:

```python
def test_operation_ids(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    ids = [op["operationId"] for path in spec["paths"].values() for op in path.values()]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", i) for i in ids)
```

- The tool description is the operation's `description`, which comes from the function
  docstring. Without a docstring Open WebUI falls back to `summary`, which is just the title-cased
  function name. Write the docstring for the model: what the tool does and when to use it.
- Only `application/json` request bodies are read, and their fields are merged with the query and
  path parameters into one flat argument list, so keep names unique across all three. A parameter
  whose schema has no `type` is presented to the model as a string; `int | None` renders as
  `anyOf`, so prefer `limit: int = 10`.
- Open WebUI gives up on the spec after 10 s (`AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA`), so keep
  `/openapi.json` fast.
- For logs and traces, global tool servers get `X-OpenWebUI-Chat-Id` and `X-OpenWebUI-Message-Id`
  with the forwarding flag, or, without sending user details, from custom connection headers set
  to `{{CHAT_ID}}` and `{{MESSAGE_ID}}`. User tool servers get neither.

## 7. An OpenAI-compatible chat endpoint over a LangGraph graph

Open WebUI and the `openai` SDK call `<base>/models` and `<base>/chat/completions`. With a base
URL ending in `/v1`, serve `GET /v1/models` and `POST /v1/chat/completions`. The full, tested code
is in [references/openai-compatible.md](references/openai-compatible.md). These are the decisions
it encodes:

- **Serve both modes.** Open WebUI sends `"stream": false` for its own tasks (titles, tags,
  follow-up suggestions) and `"stream": true` for chat. A route with
  `response_class=EventSourceResponse` always streams, so return either the JSON completion or a
  `StreamingResponse` with the SSE media type and headers that FastAPI's own SSE would add.
- **Wire format.** Each event is `data: <chat.completion.chunk JSON>\n\n`, with no `event:` line.
  The first delta is `{"role": "assistant", "content": ""}`, then come `{"content": ...}` deltas,
  then an empty delta with `"finish_reason": "stop"`, then the literal `data: [DONE]\n\n`. Every
  chunk carries the same `id`, `created` and `model`, and `"object": "chat.completion.chunk"`.
  Report a failure mid-stream as `data: {"error": {"message": ...}}` before `[DONE]`: the openai
  SDK (checked at 3.26.0) raises it as `APIError`, and Open WebUI shows it on the message. Log the
  exception and send a short message, not `str(exc)`, which can carry internal URLs and details.
- **Tool status.** The graph runs its own tools, so the stream carries no `delta.tool_calls`: an
  OpenAI client reads those as calls it must execute itself. Report progress with a chunk that has
  `"choices": []` and a top-level `"event": {"type": "status", "data": {"description": "Searching the docs", "done": false}}`.
  Open WebUI's stream parser passes a top-level `event` to its event emitter (in its source, not
  its docs). The openai SDK yields it as a chunk with empty `choices`, the shape of a usage chunk.
  End every status sequence with `"done": true`, or the last status stays animated.
- **Reading the graph.** `graph.astream(inputs, config, stream_mode=["messages", "custom"], version="v2")`
  yields `{"type", "ns", "data"}` parts. A `messages` part is `(message, metadata)`: tokens from
  every LLM call in every node, plus the messages nodes return (ToolMessages from the tools node).
  Forward text only from the node that writes the answer (`metadata["langgraph_node"]`;
  langchain 1.4's `create_agent` names it `model`), so routers and graders stay out of the reply.
  A `nostream` tag on a model only stops its tokens: a message its node returns into state still
  arrives when the node ends. Read `msg.text`, since content can be a list of blocks.
  `custom` parts carry what a tool writes with `get_stream_writer()` (Python 3.11+ in async code).
- **History.** Open WebUI sends the whole conversation every turn, so run the graph statelessly
  from `messages`. A checkpointer keyed on `X-OpenWebUI-Chat-Id` would append the full history
  again every turn, because messages without IDs count as new for `add_messages`. Edited or
  regenerated messages would also diverge from the thread.
- **Cancellation.** Under uvicorn (0.54.0 declares ASGI spec 2.3), Starlette cancels a streaming
  response when the client disconnects, and that cancels the graph run inside it. Catch
  `Exception`, never `BaseException`, so `CancelledError` propagates, and release resources in
  `finally`.
- **Keep-alive.** A hand-built `StreamingResponse` gets none of the 15 s `: ping` comments that
  FastAPI's own SSE sends. Status chunks keep the stream busy; a tool that runs for minutes should
  report progress through `get_stream_writer()`.
- **`/v1/models` stays cheap.** Open WebUI gives it 10 s (`AIOHTTP_CLIENT_TIMEOUT_OPENAI_MODEL_LIST`).

## Check before you hand it back

```bash
uv run pytest                    # passes, with no StarletteDeprecationWarning in the output
uv run fastapi dev               # serves on 127.0.0.1:8000; then, from another shell:
curl -fsS http://127.0.0.1:8000/openapi.json | jq '[.paths[][].operationId]'
curl -N http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer $APP_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model": "docs-agent", "stream": true, "messages": [{"role": "user", "content": "hi"}]}'
                                 # data: chunks, status events, then data: [DONE]
curl -si -X OPTIONS http://127.0.0.1:8000/tools/search \
  -H 'Origin: https://chat.example.com' -H 'Access-Control-Request-Method: GET' | head -5
```
