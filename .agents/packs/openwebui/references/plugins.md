# Open WebUI plugins: anatomy and rules

These rules were checked against the docs for v0.12.0. Before you rely on one, search the docs for
it (SKILL.md, section 1). Page index: <https://docs.openwebui.com/features/extensibility>.

## Every plugin

- **One file:** a top-level docstring, then the class.
  - The file's first line must be `"""` on its own. Anything above it (a comment, an import)
    and Open WebUI reads no frontmatter at all, `requirements` included.
  - Frontmatter keys: `title`, `author`, `author_url`, `git_url`, `description`, `icon_url`,
    `required_open_webui_version`, `requirements` (comma-separated pip packages) and `version`.
    Since v0.9.6, the editor fills Name, ID and Description from `title` and `description`.
  - Class names: `Tools` lives under Workspace > Tools. `Pipe`, `Filter`, `Action` and `Event` are
    Functions, which only admins can create.
- **Valves:** `Valves` holds admin settings and `UserValves` holds per-user settings; a user's
  values arrive in `__user__["valves"]`.
  - `__init__` must set `self.valves = self.Valves()`. Saved admin values load only onto an
    instance that already has `valves`.
  - Hide secrets in the UI with `Field("", json_schema_extra={"input": {"type": "password"}})`.
  - Valves are stored as plaintext unless `ENABLE_VALVE_ENCRYPTION=true`, which derives its key
    from `WEBUI_SECRET_KEY`. Rotating that key makes encrypted values unreadable.
- **Async:**
  - Plugin entry points are `async def`.
  - Since 0.9.0, database methods on the `open_webui.models.*` classes, and anything that calls
    one, must be awaited. Database sessions come from `get_async_db_context`.
  - Use `httpx.AsyncClient` for HTTP. The pipe docs warn that sync `requests` blocks the event
    loop for every user.
- **No execution timeout.** Nothing kills a running pipe, tool or action except an exception, a
  restart, or a stop. The chat's stop button calls `POST /api/tasks/chat/{chat_id}/stop`.
  `__event_call__` waits indefinitely unless `WEBSOCKET_EVENT_CALLER_TIMEOUT` is set.
- **Requirements:** `requirements` are pip-installed into Open WebUI at startup and on save
  (`ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS`, on by default). Keep them few, and pin them.

## Tools

- **Every public method is a tool.** Helper methods need a leading `_`.
- **The method docstring is what the model reads.** The text before the first `:param` becomes
  the tool's description, and each `:param name:` becomes that argument's description. Only the
  reST form is parsed: a Google-style `Args:` block ends up in the tool's description, and
  anything after `:return:` is never sent.
- **Type hints build the JSON schema.** An argument without a hint becomes a string.
  `Optional[X]` collapses to `X`. Arguments whose names start with `__` are hidden from the model.
- **Return a `str`, `dict` or `list`.** A dict is JSON-encoded, a bare list is wrapped as
  `{"results": [...]}`, and a string that starts with `data:image/` is attached as an image.
- **Reserved arguments:** `__event_emitter__`, `__event_call__`, `__user__`, `__metadata__`,
  `__messages__`, `__files__`, `__model__`, `__id__`, `__chat_id__`, `__message_id__`,
  `__request__` and `__oauth_token__`. `__model__` is the task model when one is configured, so
  read `__metadata__["model"]` for the model the user is chatting with.

## Native mode and events

```python
def is_legacy_mode(__metadata__) -> bool:
    # Native is the default since v0.10.0 and carries no "native" string when unset.
    return (__metadata__ or {}).get("params", {}).get("function_calling") == "legacy"
```

- **Overwritten in Native mode:** `message`, `chat:message:delta`, `chat:message` and `replace`,
  because the server keeps replacing message content with full snapshots.
- **Work in Native mode:** `status`, `notification`, `source`/`citation`, `files`, `embeds`,
  `confirmation`, `input`, `execute` and `chat:message:follow_ups`.
- **Only these short names are saved to the database:** `status`, `message`, `replace`, `embeds`,
  `files` and `source` (or `citation`). The long names render the same in the browser but aren't
  saved. Nothing is saved for a temporary chat.
- **`status` takes `{description, done, hidden}`.** Always end with `done: true`.
- **The confirm and input dialogs need `__event_call__`:**
  `await __event_call__({"type": "confirmation", "data": {"title": ..., "message": ...}})`.
  It doesn't raise when nobody can answer: it returns a dict with an `error` key (tab closed, or
  `WEBSOCKET_EVENT_CALLER_TIMEOUT` passed). A dict is truthy, so test for `error` before
  `if result:`, or a closed tab reads as "yes".

## Action (a button under each assistant message)

- **Signature:** `async def action(self, body, __user__=None, __event_emitter__=None, __event_call__=None)`.
- **Return value:** to change the chat, return `{"messages": [...]}`, each entry the `id` of an
  existing message plus the fields to overwrite. Anything else is dropped, so a bare
  `{"content": "..."}` does nothing. An inline `HTMLResponse` becomes a Rich UI embed.
- **Multiple buttons:** a class attribute `actions = [{"id": ..., "name": ..., "icon_url": ...}]`
  defines one button per entry, and `__id__` says which one was clicked. A module-level list is
  ignored.
- **Order and scope:** a `priority` valve orders the buttons, lowest first (default 0). A Global
  toggle shows the action on every model; otherwise you enable it per model.
- **Icons:** host `icon_url` at a URL. Base64 icons go out in `/api/models` on every page load.

## Filter (rewrites traffic for a model or globally)

Filters have four hooks:

- **`inlet`** runs once per user turn.
- **`request`** (v0.11.2+) runs before every call to the provider, which includes every hop of a
  tool loop. Write it to be idempotent, because it sees a body it has already changed.
  - By the time `request` runs, `files`, `tool_ids` and `features` are gone, while the resolved
    `tools` and the retrieved `<source>` chunks are present.
- **`stream`** runs on each streamed chunk.
- **`outlet`** runs after the reply. Since v0.10.0 it also runs for direct API callers
  (`ENABLE_API_OUTLET_FILTERS`), but the filtered text never reaches the HTTP response. It is
  saved to the chat instead.

Other Filter rules:

- **User chip:** `self.toggle = True` gives users a chip to switch the filter per chat. Never read
  `self.toggle` at runtime. When the user switches the filter off, the hooks simply don't run.
- **Order:** a `priority` valve sets the order, lowest first.
- **Global:** a filter that is both Global and active is forced on for every model.
- **Exceptions:** what a raised exception does depends on the hook:
  - in `inlet`, or in the first `request` of a turn, it aborts the turn;
  - in `stream`, the WebUI path drops that one chunk;
  - in `outlet`, it is only logged.

## Event function (v0.10.0+)

`class Event` with `async def event(self, event, __event_id__=None, __event_name__=None, ...)`
reacts to system events such as `auth.signup`, `chat.deleted`, `system.startup` and
`config.updated`, rather than to chat requests. Use it for audit logs, provisioning and alerts.

## Rich UI embeds

- **Return an embed from a Tool:**
  `HTMLResponse(content=html, headers={"Content-Disposition": "inline"})`.
  - By default the model is told only `"<tool_name>: Embedded UI result is active and visible to the user."`.
    To tell it what the embed shows, return a tuple `(HTMLResponse, context)`, where `context` is a
    `str`, `dict` or `list`.
- **From an Action:** return an `HTMLResponse`, or a tuple
  `(html, {"Content-Disposition": "inline", "Content-Type": "text/html"})`.
- **From a Pipe that runs its own tool loop:** the middleware never sees the tool result, so emit
  `{"type": "embeds", "data": {"embeds": [html]}}` yourself and return a text summary to the
  model. Pass `"replace": true` to update one live widget in place.
- **Sandbox:** `allow-scripts` and `allow-downloads` are always set.
  - "iframe Sandbox Allow Same Origin" and "Allow Forms" are per-user switches in Settings >
    Interface, and both are off by default. Embeds attached to an assistant message always allow
    forms.
  - Without same-origin, the embed has no access to Open WebUI's DOM, cookies or API, the parent
    can't measure it, and `window.args` (the tool's arguments, a JSON string) isn't injected.
  - With same-origin, Alpine.js and Chart.js are injected automatically when the HTML uses them.
  - Build for same-origin off. The docs say to turn it on only for content you trust, because the
    embed then shares the page's context. Never ask users to turn it on for HTML that a model
    or another user wrote.
- **Height:** report it from inside the embed with
  `parent.postMessage({type: "iframe:height", height: document.documentElement.scrollHeight}, "*")`.
- **UI frameworks (React, shadcn and the like):** build to one self-contained HTML document with
  the JS and CSS inline, or loaded from a CDN. The `frontend-design` skill (react pack) applies to
  what goes inside.

## Reference code

- **Classic298/open-webui-plugins** (<https://github.com/Classic298/open-webui-plugins>): BSD-3-Clause,
  by a core Open WebUI contributor, updated 2026-10-11. Worth reading:
  - `inline-visualizer-v2`: a Rich UI tool;
  - `mcp-app-bridge`: renders MCP Apps `ui://` resources as embeds;
  - `better-banners` and `interface-defaults`: instance UX.
- **The community site** (openwebui.com): Featured or popular status there is not a security
  review. Read the code before you import anything, because it runs as Open WebUI on the server.
