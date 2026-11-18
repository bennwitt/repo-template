---
name: llama-app
description: "Llama desktop app (llama.app) and llama serve router mode: point an app, agent, LibreChat or Open WebUI at localhost:9931/v1, pick and pin a GGUF model and INI preset, idle unload, HF cache, models.user.ini, the stdio MCP client, --api-key exposure. Use when connecting to or configuring either."
license: MIT
compatibility: "Llama app on macOS or Windows 11; the llama CLI on Linux. The lookups need curl and gh."
---

# Llama app and `llama serve` as a local model endpoint

The Llama app (llama.app, by the llama.cpp team and Hugging Face) is a menu-bar or tray app that
runs `llama serve` in router mode on `http://localhost:9931/v1`: models download once into the
Hugging Face cache, load on the first request and unload when idle. This skill was checked on
2026-11-18 against Llama-macOS 0.48.0 (2026-11-17, engine b12375 on llama.cpp 1.0),
Llama-Windows v0.14.1 (2026-10-30; app source read on `main`), llama.cpp v1.0.0 (2026-11-13,
`a6d1a74`; `tools/server/README.md` and `docs/preset.md` on `master` match the tag for every flag
cited) and the llama.app docs. The companion `llama-cpp` skill in this pack covers building,
quantizing, benchmarking and multi-GPU; the global `compose-gpu-serving` skill covers Docker
Compose; `local-model-serving` covers vLLM and Ollama alongside llama.cpp. None of that is
repeated here. What each app launches, where its cache, settings and overrides live, and its
network options are in [references/apps.md](references/apps.md).

## 1. Look it up for the version you run

- CLI build: `llama --version`. Releases:
  `gh api repos/ggml-org/Llama-macOS/releases --jq '.[0:3][] | [.tag_name, .published_at] | @tsv'`,
  the same for `ggml-org/Llama-Windows` (tags carry a `v`) and `ggml-org/llama.cpp`, whose
  versioned tags (`v1.0.0`) sit among the nightly `b12xxx` builds.
- Docs: every llama.app docs page is served as Markdown at `https://llama.app/docs/<page>.md`,
  with pages `introduction`, `installation`, `quickstart`, `cli`, `serve`, `api`, `webui` and
  `agents`.
- Server flags and router endpoints at your tag:
  `gh api 'repos/ggml-org/llama.cpp/contents/tools/server/README.md?ref=v1.0.0' -H 'Accept: application/vnd.github.raw'`;
  INI presets: the same path with `docs/preset.md`. `llama serve --help` lists every flag with
  its `LLAMA_ARG_*` environment form.
- What the app launched: macOS `readme.md` ("Custom model settings", "Network access") and
  `Llama/Server/LlamaServer.swift` (`buildLaunchSpec`); Windows
  `LlamaApp.LlamaCpp/LlamaManager.cs` (`BuildServeArguments`).

## 2. Point a client at it

The base URL is `http://127.0.0.1:9931/v1` and the model id is what `GET /v1/models` reports,
`org/repo:QUANT` for a cached Hugging Face model. In router mode every request must name the
model (`model` in a POST body, `?model=` on a GET), and the first request loads it, so allow a
slow first reply. Chat, completions, Responses, embeddings, rerank and an Anthropic-style
`/v1/messages` are all there; streaming, tool calls, `response_format` and vision work through
the OpenAI shapes.

- **OpenAI SDK:** `OpenAI(base_url="http://127.0.0.1:9931/v1", api_key="no-key-required")`;
  any string serves as the key until `--api-key` is set.
- **Codex CLI and ChatGPT desktop** (from llama.app/docs/agents): in `~/.codex/config.toml`
  `model = "<model id>"`, `model_provider = "llamacpp"`, and a `[model_providers.llamacpp]`
  table with `name = "llama.cpp"`, `base_url = "http://127.0.0.1:9931/v1"`,
  `wire_api = "responses"`, `requires_openai_auth = false`, `supports_websockets = false`.
  **Pi:** `/login llama.cpp`, then `/model`. The docs ask for a context of at least 32k tokens
  for agents; set it per model in the preset (section 3).
- **Open WebUI:** add the URL (ending in `/v1`) as an OpenAI API connection under Settings >
  Admin > Connections, then Verify Connection. The `openwebui` skill has the rest.
- **LibreChat:** an `endpoints.custom` entry in `librechat.yaml` with `name`, `apiKey` (any
  value), `baseURL`, `models: {default: [<model id>], fetch: true}`, `titleConvo`, `titleModel`
  and `modelDisplayLabel`, then restart LibreChat. The `librechat` skill has the rest.
- **From a container:** on Linux a container cannot reach a host process bound to 127.0.0.1,
  not even through `host.docker.internal`. Either run `llama serve` as a Compose service
  (`compose-gpu-serving`), or bind the host server to a non-loopback address with an API key
  (section 6) and point the container at `host.docker.internal` with
  `extra_hosts: ["host.docker.internal:host-gateway"]`.

## 3. Pick and pin a model and a preset

- **Download into the cache** with `llama serve -hf org/repo:QUANT` (or `llama cli -hf ...`;
  the quant defaults to Q4_K_M, and the mmproj comes along for multimodal repos). `llama cli -cl`
  lists the cache. A router started afterwards lists the model; a running router does so on
  `GET /models?reload=1`. The `huggingface-local-models` skill covers choosing the GGUF.
- **Router sources**, all optional: the cache, `--models-dir DIR` (one GGUF per file, or a
  subdirectory per model for shards and an `mmproj*` file), and `--models-preset FILE`.
- **Preset file:** an INI whose sections are model ids; keys are `llama serve` options without
  dashes, short forms (`c`, `ngl`) and `LLAMA_ARG_*` names also work, and `[*]` holds defaults.
  Precedence: command-line arguments, then the model's section, then `[*]`. A section whose name
  is not a cached model needs `model = /abs/path.gguf` or `hf = org/repo:QUANT`. The router owns
  `host`, `port`, `api-key`, `hf-repo` and `alias` and overwrites them. Preset-only keys:
  `load-on-startup`, `stop-timeout` (seconds, default 10) and `dedup-cache-models`.
- **Pin the context** with `c = 32768` (or `ctx-size`) in the model's section: with `--fit` on
  (the default) an instance otherwise takes the largest context that fits at load time, which
  starves the other models.
- **Shared presets on Hugging Face:** a model repo whose root holds `preset.ini` loads with
  `llama serve -hf user/repo`, and `-hf user/repo:section` picks a named section; CLI flags
  still override it. The doc's warning: only use presets you trust.
- **In the apps,** the app writes the preset; put per-model keys in `models.user.ini` (macOS) or
  the model's settings (Windows). Details in [references/apps.md](references/apps.md).

## 4. Loading, unloading and memory

- **Autoload** is on: an unloaded model loads on its first request. With `--no-models-autoload`,
  or `?autoload=false` on one request, that request fails instead. `POST /models/load` and
  `POST /models/unload` with `{"model": "<id>"}` do it by hand; `GET /models` shows `status`
  (`unloaded`, `loading`, `loaded`, `sleeping`, `downloading`, `incomplete`; a crashed load is
  `unloaded` with `failed: true` and an `exit_code`) and, with the margin below, a `memory` block
  with `min`, `max` and `effective`.
- **Count cap:** `--models-max N` (default 4, 0 = unlimited) evicts least recently used.
- **Memory cap:** `--models-memory-margin N` keeps N MiB free per device and unloads idle models
  (LRU) until the new one fits; a model mid-request is never unloaded, and one that still does
  not fit is loaded anyway and `--fit` decides. Projectors and draft models are not counted yet.
  The router measures each model in a short-lived child, so `memory.status` reads `measuring`
  right after start. The macOS app runs `--models-max 0` with this margin; the Windows app runs
  `--models-max 1`.
- **Idle unload:** `--sleep-idle-seconds N` (default -1, off; both apps pass 300) unloads the
  model and its KV cache after N seconds without a task and reloads on the next one; the status
  reads `sleeping`. `GET /health`, `/props`, `/models` and `/metrics` neither wake it nor reset
  the timer, so they are safe for monitoring.

## 5. The built-in MCP client

`--mcp-servers-config mcp.json` (or `--mcp-servers-json '<json>'`) takes a Cursor-style file:
`{"mcpServers": {"name": {"command": "...", "args": [], "env": {}, "cwd": "...", "timeout_ms": 30000}}}`.
Only stdio servers work: each is spawned once at startup to list its tools, then respawned on
demand per call, and its tools appear as `<server>_<tool>` in the chat UI, with or without
`--tools`. The child runs with the server's privileges, so declare only commands you trust;
`--cors-origins` then defaults to `localhost`. `--ui-mcp-proxy` is a different thing: a CORS
proxy so the web UI can reach public remote MCP servers, and it refuses loopback and private
addresses. The macOS app's "agent mode" passes `--agent`, which turns on the server's file tools
and the UI's CORS and MCP proxy; it is off by default. `--help` marks all of this experimental.

## 6. Exposing it beyond loopback

The server binds `127.0.0.1` and has no authentication by default, and the control API
(download, load, delete) shares the port with chat. Keep it that way on a single workstation.
Otherwise:

- Add `--api-key KEY` (comma-separated for several), `--api-key-file FILE`, or the
  `LLAMA_API_KEY` environment variable (what the Windows app uses, so the key is in neither argv
  nor a file). Clients send `Authorization: Bearer KEY`; `/health` stays public.
- On a LAN, set `--cors-origins` to the front end's origin. On a public address, the server
  README asks for an API key behind a reverse proxy. `--allow-unauthenticated-tools` exists
  only for trusted networks: tools and MCP on a non-loopback address are otherwise refused
  without a key.
- **macOS app:** Settings > Allow network access offers Tailscale (authenticated and encrypted,
  the laptop option) or This network (`0.0.0.0`, no password; the readme says never with agent
  mode on a network you do not own). **Windows app:** any non-loopback bind makes the app
  generate a key and require it. Both are detailed in [references/apps.md](references/apps.md).

## Check before you hand it back

```bash
llama --version
curl -fsS http://127.0.0.1:9931/health                      # 200; no key needed
curl -fsS http://127.0.0.1:9931/v1/models | jq '.data[].id'  # the exact id to pin
curl -fsS http://127.0.0.1:9931/models | jq '.data[] | {id, status: .status.value}'
curl -fsSN -H 'Content-Type: application/json' \
  -d '{"model":"<id>","stream":true,"messages":[{"role":"user","content":"hi"}]}' \
  http://127.0.0.1:9931/v1/chat/completions                  # chunks, then data: [DONE]
```

Then confirm the model's `status` is `loaded`, that after the idle time it reads `sleeping` and
the next chat still answers, and that a preset key took effect (`.status.args` in `GET /models`
shows the instance's arguments). With a key set, repeat the chat call with and without
`Authorization: Bearer` and expect 401 on the second.
