# Open WebUI and Claude Code against Muse Glimmer on vLLM

Both clients are configured per machine or per instance, not per repository. Keep their settings
out of committed files.

## Open WebUI

Checked against Open WebUI v0.11.4 (2026-09-21). v0.12.0 was released on 2026-10-10, less than
7 days before this check, so it wasn't used. To see newer releases, run
`gh release list -R open-webui/open-webui -L 5`.

- **Connection.** Add an OpenAI-compatible connection with base URL `http://<vllm-host>:8000/v1`
  and the vLLM `--api-key`, or any placeholder if there is none. The `OPENAI_API_BASE_URL` and
  `OPENAI_API_KEY` environment variables set the same thing, but only as defaults: once a
  connection is saved in the admin settings, the saved one wins (unless
  `ENABLE_PERSISTENT_CONFIG=false`), so changing the variables later does nothing. If Open WebUI
  runs in a container, `localhost` is that container, so use the Compose service name instead,
  for example `http://vllm:8000/v1`.
- **Function Calling: Native.** Native is the default in v0.11.4 and uses the server's
  `tool_calls`. Legacy injects its own prompt-based tool protocol, which conflicts with
  Glimmer's format.
- **Sampling.** Set temperature 1.0, top_p 0.95 and top_k 64 on the model, unless the server
  already applies them with `--override-generation-config`. An admin sets these in Workspace ->
  Models, and they apply to every chat that doesn't set its own. For an OpenAI connection,
  `top_k` is passed through into the request body.
- **Reasoning strength.** Leave Reasoning Effort unset, because it sends `reasoning_effort`, which
  the Muse template ignores. Instead, add a custom parameter named `chat_template_kwargs` with the
  value `{"reasoning_strength": "medium"}`. Open WebUI JSON-decodes a custom parameter's value and
  merges it into the request body (`apply_model_params_to_body_openai` in
  `backend/open_webui/utils/payload.py`).
- **System prompt.** A model system prompt replaces the template's built-in one, and the date line
  goes with it. Write `Today is {{CURRENT_DATE}}.` into the prompt; Open WebUI substitutes the
  server's date.
- **Reasoning display.** Open WebUI reads `delta.reasoning` and shows it as the model's reasoning.
  It doesn't send reasoning back to an OpenAI connection, because v0.11.4 replays it only to
  Ollama and llama.cpp providers. So in native multi-step tool use, each step starts without the
  earlier reasoning. That is a limitation to accept, not a setting to fix.

## Claude Code

Claude Code talks to vLLM's Anthropic Messages endpoint (`/v1/messages`). Use a launcher script
or shell function, like the one below, rather than an `env` block in `settings.json`. A
`settings.json` that is committed, or synced across machines, would send every session to the
local model.

```bash
#!/usr/bin/env bash
# Run Claude Code against a local vLLM serving Muse Glimmer.
export ANTHROPIC_BASE_URL="${MUSE_GLIMMER_HOST:-http://127.0.0.1:8000}"   # host only: no /v1
export ANTHROPIC_AUTH_TOKEN="${MUSE_GLIMMER_API_KEY:-unused}"           # required; any value without --api-key
export ANTHROPIC_MODEL=muse-glimmer
export ANTHROPIC_DEFAULT_OPUS_MODEL=muse-glimmer
export ANTHROPIC_DEFAULT_SONNET_MODEL=muse-glimmer
export ANTHROPIC_DEFAULT_HAIKU_MODEL=muse-glimmer
export CLAUDE_CODE_SUBAGENT_MODEL=muse-glimmer
export CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1      # v2.1.257+: subagents can't pick another model
export CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072   # the server's max_model_len from GET /v1/models
unset ANTHROPIC_API_KEY
exec claude "$@"
```

Why each line is there:

- **`ANTHROPIC_BASE_URL` is the host only.** Claude Code appends `/v1/messages` itself.
- **`ANTHROPIC_AUTH_TOKEN`, not `ANTHROPIC_API_KEY`.** vLLM's `--api-key` check reads only
  `Authorization: Bearer`, on `/v1` routes. `ANTHROPIC_API_KEY` goes out as `X-Api-Key`, which
  vLLM ignores. If a real Anthropic key were set, it would also be sent to the local server; the
  `unset` line prevents that.
- **Every model setting.** Plan Mode, subagents and background tasks each pick a model through a
  different setting, and any one left unset tries to reach a Claude model that vLLM doesn't
  serve. The served name must not contain `/`.
- **`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`.** `CLAUDE_CODE_SUBAGENT_MODEL` is only a default: a
  `model` field in a subagent definition, or a model Claude passes when it starts one, wins over
  it, and a full Claude model ID there bypasses the aliases above. The force flag makes every
  subagent, teammate and workflow agent use `CLAUDE_CODE_SUBAGENT_MODEL`. It needs Claude Code
  v2.1.257 or later; older versions ignore it.
- **`CLAUDE_CODE_MAX_CONTEXT_TOKENS`.** Claude Code doesn't recognize `muse-glimmer`, so it
  assumes a context window of its own, and compaction then triggers at the wrong point. Set the
  variable to the server's `max_model_len`. It applies directly because the name doesn't start
  with `claude-`.
- **Effort controls do nothing here.** For a model ID it doesn't recognize, Claude Code doesn't
  send `/effort`, `--effort`, `effortLevel` or `CLAUDE_CODE_EFFORT_LEVEL` at all, unless
  `CLAUDE_CODE_ALWAYS_ENABLE_EFFORT=1` is set. When effort is sent, vLLM maps it to
  `reasoning_effort`, which the template ignores. Set strength on the server with
  `--default-chat-template-kwargs '{"reasoning_strength": "high"}'`. That value then applies to
  every client of that server that doesn't send its own.
- **Leave `ENABLE_TOOL_SEARCH` unset.** Meta's coding-agents guide sets it to `true`, but that
  guide is for Meta's hosted API. The Muse chat template renders every tool, deferred or not,
  and skips `tool_reference` blocks, so tool search saves nothing here. Left unset, Claude Code
  loads MCP tools up front for a non-Anthropic host.

The variables were checked against the Claude Code environment-variable and model-configuration
docs (<https://code.claude.com/docs/en/env-vars>,
<https://code.claude.com/docs/en/model-config>,
<https://code.claude.com/docs/en/sub-agents>), vLLM's Claude Code integration page and its
Anthropic endpoint source at v0.31.0. Claude Code changes often, so re-read the env-vars page
before relying on a variable not listed here.
