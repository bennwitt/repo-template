# Clients for a local endpoint

Checked on 2026-10-14 against langchain-openai 1.6.7, langchain-deepseek 1.1.1, the openai
SDK 3.26.0, the Claude Code docs at
`https://code.claude.com/docs/en/` and vLLM v0.31.0.

## Any OpenAI client

- The base URL ends in `/v1`: `http://127.0.0.1:8000/v1` for vLLM. The openai SDK insists on
  some `api_key` even when the server has none.
- `GET /v1/models` lists the served names; `root` is the checkpoint behind each one.
- vLLM-only request fields (`chat_template_kwargs`, `thinking_token_budget`, `top_k`) go in
  `extra_body`.

## LangChain

`ChatOpenAI` targets the official OpenAI API only: its module docstring says it does not extract
non-standard response fields, and names vLLM among the providers affected. A vLLM response with
`reasoning` set becomes an `AIMessage` with empty `additional_kwargs`. Content and tool calls
come through.

```python
import os
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model=os.environ["LOCAL_MODEL"],            # the --served-model-name
    base_url=os.environ["LOCAL_BASE_URL"],      # e.g. http://127.0.0.1:8000/v1
    api_key=os.environ.get("VLLM_API_KEY", "EMPTY"),
    use_responses_api=False,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
```

- `use_responses_api=False`: `ChatOpenAI` picks Chat Completions or Responses partly from the
  model name, whatever `base_url` says, so set it explicitly.
- When the reasoning text matters, call the openai SDK and read `message.reasoning`, or use
  `ChatDeepSeek(model=..., api_base=..., api_key=...)` from langchain-deepseek, which copies
  vLLM's `reasoning` into `additional_kwargs["reasoning_content"]`, streaming included. Always
  pass `api_base`: without it (or `DEEPSEEK_API_BASE`) requests and the key go to
  `https://api.deepseek.com/v1`. PyPI has no `langchain-vllm` package.
- For agents and graphs built on the model, use the `langchain` pack's skills
  (`langchain-fundamentals`, `deep-agents-core`).

## Claude Code

vLLM serves the Anthropic Messages API at `/v1/messages`, so Claude Code can run on a local
model. Keep these variables in a launcher script rather than a `settings.json`: user settings
apply to every session, and portable settings reach every machine.

```bash
#!/usr/bin/env bash
# claude-local: Claude Code against a local vLLM server
set -euo pipefail
model=qwen3-14b                                       # vLLM --served-model-name, no "/"
unset ANTHROPIC_API_KEY                               # keep a real Anthropic key off the local server
export ANTHROPIC_BASE_URL=http://127.0.0.1:8000       # server root, no /v1
export ANTHROPIC_AUTH_TOKEN="${VLLM_API_KEY:-local}"  # sent as Authorization: Bearer
export ANTHROPIC_MODEL="$model" CLAUDE_CODE_SUBAGENT_MODEL="$model"
export CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1             # Claude Code 2.1.257+
export ANTHROPIC_DEFAULT_OPUS_MODEL="$model" ANTHROPIC_DEFAULT_SONNET_MODEL="$model"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="$model" ANTHROPIC_DEFAULT_FABLE_MODEL="$model"
export CLAUDE_CODE_MAX_CONTEXT_TOKENS=40960           # the server's --max-model-len
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192             # prompt + this must fit --max-model-len
exec claude --strict-mcp-config --mcp-config "$HOME/.config/claude-local/mcp.json" "$@"
```

Why each line:

- **Model name.** vLLM's Claude Code page says names containing `/` do not work. Point every
  alias variable and the subagent model at the served name, so no request asks for a Claude
  model the server lacks. A subagent definition with its own `model` field still wins over
  `CLAUDE_CODE_SUBAGENT_MODEL` unless `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` is set.
- **Key.** `ANTHROPIC_AUTH_TOKEN` is sent as `Authorization: Bearer`, the only header vLLM's
  key check reads. `ANTHROPIC_API_KEY` would be sent as `X-Api-Key` to whatever host
  `ANTHROPIC_BASE_URL` names, which is why the launcher unsets it.
- **Settings win.** In most sessions an `env` entry in a Claude Code settings file replaces the
  shell's value for the same variable, so a stray `ANTHROPIC_BASE_URL` or `ANTHROPIC_API_KEY`
  there undoes the launcher. In the session, `/status` shows the `Anthropic base URL` and
  `Auth token` lines actually in use.
- **Limits.** For a model ID it does not recognise, Claude Code assumes a context window that
  is not the server's and defaults to 32,000 output tokens. `CLAUDE_CODE_MAX_CONTEXT_TOKENS`
  applies directly to an ID that does not start with `claude-`, so compaction happens before
  vLLM refuses. vLLM rejects any request whose prompt plus `max_tokens` exceeds
  `--max-model-len`, so keep the output cap well below it.
- **Context size.** Claude Code's system prompt and tool definitions fill much of a small
  window; Ollama's Claude Code page recommends at least 64k tokens. Qwen3-14B stops at 40,960
  natively, so for more pick a model with a longer native window, or apply the recipe's YaRN
  override, which the recipe warns can cost quality on short prompts.
- **MCP.** Claude Code turns tool search off when `ANTHROPIC_BASE_URL` is not an Anthropic host,
  so every MCP tool definition goes into every request. `--strict-mcp-config` loads only the
  servers in `--mcp-config` (`{"mcpServers": {}}` for none). `ENABLE_TOOL_SEARCH=true` keeps
  tool search on for such a host; requests then fail unless the server accepts
  `tool_reference` blocks. vLLM v0.31.0's Anthropic endpoint accepts them; test with your model
  before relying on it.
- **Tools.** The model needs a working `--tool-call-parser`: run the tools request from the
  SKILL.md check before starting Claude Code.

For Ollama, Ollama's docs give `ollama launch claude`, or the same variables with
`ANTHROPIC_BASE_URL=http://localhost:11434`, `ANTHROPIC_AUTH_TOKEN=ollama` and
`ANTHROPIC_API_KEY=""`.
