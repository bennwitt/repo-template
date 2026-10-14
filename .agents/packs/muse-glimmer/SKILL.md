---
name: muse-glimmer
description: "Meta Muse Glimmer served by vLLM, and its clients (LangChain, Open WebUI, Claude Code): serve flags, sampling the quantized checkpoints lack, reasoning_strength (reasoning_effort does nothing), 0..N tool calls, schemas vLLM doesn't enforce, replaying reasoning, a smoke test. Use when code, config or a client targets a muse-glimmer model on vLLM."
---

# Muse Glimmer on vLLM

Muse Glimmer is Meta's open-weight 30B vision-language model for local agents: 131,072-token
context, text and images in, text out, Apache-2.0 plus Meta's
[Usage Policy](https://huggingface.co/meta-models/Muse-Glimmer-30B/blob/main/USAGE_POLICY.md).
It writes reasoning and tool calls in its own channel format, and vLLM's `muse_glimmer` parsers
turn them into standard OpenAI fields. Getting the server to start is the easy part. What goes
wrong is quieter: sampling that isn't Meta's, a reasoning control that does nothing, wrong
assumptions about tool calls and structured output, and clients that drop the `reasoning` field.

Checked on 2026-10-14 against vLLM v0.28.0 and v0.31.0 source, the Hugging Face checkpoint
files, Meta's docs, langchain-openai 1.6.7, Open WebUI v0.11.4 and the Claude Code docs. Before
you assert a flag for a newer release, re-read the sources at the end. Other skills cover the
rest: `compose-gpu-serving` for the compose file, GPU sharing and image digests;
`local-model-serving` for vLLM in general; and the `langchain` pack skills
(`langchain-fundamentals`, `deep-agents-core`) for LangChain and Deep Agents themselves.

## 1. Find out what is serving

- `GET /v1/models` returns three fields that matter: `id` is the served name every client sends,
  `root` is the checkpoint, and `max_model_len` is the context length.
- The checkpoint decides two things the server doesn't report:

| Checkpoint | VRAM (vLLM recipe) | Sampling in `generation_config.json` | Chat template |
|---|---|---|---|
| `meta-models/Muse-Glimmer-30B` (BF16) | 72 GB | yes | current |
| `RedHatAI/Muse-Glimmer-30B-FP8-block` | 40 GB | none | older |
| `Inferact/Muse-Glimmer-30B-NVFP4-W4A4` | 31 GB, Blackwell only | none | older |

  `nvidia/Muse-Glimmer-30B-NVFP4` matches Inferact's on both counts: no sampling and the older
  template. To check any other copy, read
  `https://huggingface.co/<repo>/raw/main/generation_config.json` and `chat_template.jinja`.
- vLLM support (#51655) first shipped in v0.28.0. On GPUs without native FP8, such as Ampere,
  vLLM runs FP8 weights through its Marlin kernel. Marlin couldn't load compressed-tensors
  block-FP8, the format of the RedHatAI checkpoint, until v0.29.0 (#52966), so use v0.29.0 or
  later on those GPUs.
- Meta's vLLM page still says support is unmerged and points at `vllm/vllm-openai:muse-glimmer`,
  a pre-release image built on 2026-08-11. Use a release tag instead. On 2026-10-14 the newest
  release at least 7 days old was v0.31.0 (2026-10-05). To find a newer one, run
  `gh release list -R vllm-project/vllm -L 5`, take the newest release at least 7 days old, and
  pin it by digest.

## 2. Serve it

```bash
vllm serve RedHatAI/Muse-Glimmer-30B-FP8-block \
  --served-model-name muse-glimmer \
  --enable-auto-tool-choice --tool-call-parser muse_glimmer \
  --reasoning-parser muse_glimmer \
  --generation-config auto \
  --override-generation-config '{"temperature": 1.0, "top_p": 0.95, "top_k": 64}' \
  --default-chat-template-kwargs '{"reasoning_strength": "high"}'
```

- The `vllm/vllm-openai` image's entrypoint is already `vllm serve`, so pass the model and flags
  as the container command. Parser names use underscores; the hyphenated spelling is rejected.
  Run both parsers together, because they key off the same channel markers.
- vLLM listens on every interface unless you pass `--host`, and `--api-key` guards only routes
  such as `/v1`; `/tokenize` and `/metrics` stay open. When you run it directly on a machine, add
  `--host 127.0.0.1`. In a container, leave the host alone and publish the port on loopback
  (`127.0.0.1:8000:8000`), as `compose-gpu-serving` shows.
- Keep `/` out of the served name, because Claude Code can't send such a name.
- `high` is already the template's default strength. The flag is there so you have one place to
  change it for clients that can't send the template argument, such as Claude Code (section 4).
- Use the template that ships with the checkpoint. Neither `--chat-template` nor
  `--trust-remote-code` is needed, since no checkpoint ships Python code.
- Stop tokens come from `generation_config.json` (`[200001, 200008]`). Never add 200007
  (`<|eom|>`): it ends the message before any later tool calls are written.
- On an RTX 5090 the recipe found that the FP8-block checkpoint fails to load in DeepGEMM
  (`Unknown SF transformation`, vllm#51884). Its workaround is to set `VLLM_USE_DEEP_GEMM=0` and
  `VLLM_MOE_USE_DEEP_GEMM=0`.

## 3. Sampling

Meta's settings are temperature 1.0, top_p 0.95 and top_k 64. Never run greedy: the recipe found
that `temperature: 0` isn't even reproducible. `--generation-config auto`, vLLM's default, loads
sampling values only when the checkpoint's `generation_config.json` has them, and only the BF16
base does. On the quantized copies vLLM silently uses its neutral defaults (top_p 1.0, top_k off).
`--override-generation-config` is merged over `auto`, so it fixes every checkpoint. Confirm it in
the startup log:

```text
Default vLLM sampling parameters have been overridden by the model's `generation_config.json`: `{...}`
```

If that line is missing, no sampling defaults were applied. A client that sets sampling per
request must send all three values. `top_k` isn't an OpenAI parameter, so it goes in `extra_body`.

## 4. Reasoning

- Glimmer always reasons. vLLM returns the reasoning as `message.reasoning` (`delta.reasoning`
  when streaming). `reasoning_content` is the deprecated name, still accepted on input.
- Strength is `low`, `medium`, `high` (the default) or `xhigh`. The only control that reaches
  the template is the `reasoning_strength` template argument:
  - per request: `"chat_template_kwargs": {"reasoning_strength": "medium"}`, inside
    `extra_body` in the OpenAI SDK and LangChain;
  - server-wide: `--default-chat-template-kwargs`. A request's value overrides it.
- `reasoning_effort` is a silent no-op. vLLM passes it to the template as a variable named
  `reasoning_effort`, which the Muse template never reads. That covers `reasoning_effort` in the
  OpenAI SDK and LangChain, Open WebUI's Reasoning Effort, and Claude Code's effort level, which
  vLLM's Anthropic endpoint maps to `reasoning_effort`. An open pull request (vllm#54186) would
  map it to `reasoning_strength`, so check the release notes of anything newer than v0.31.0.
- Set strength through the template argument, not with a `Reasoning strength: …` line in the
  system prompt, even though the model card and the recipe show that line. The older template
  on the quantized checkpoints appends its own line after yours, so the prompt carries two
  conflicting lines. Only the current BF16 template removes the duplicate.
- Reasoning runs to thousands of tokens. Stream long requests, and leave `max_tokens` generous
  or unset: the recipe saw a tight budget end with empty `content` and `finish_reason: "stop"`.
- In a tool loop, send each assistant message back with its `reasoning`. vLLM copies it into
  `reasoning_content`, which the template renders as the model's earlier thinking, and Meta's
  prompting guide says to replay reasoning this way. Without it the model sees its earlier tool
  calls but not why it made them.

## 5. Tool calls and structured output

- Expect 0..N calls per response. Meta's docs say one call per turn, and its vLLM page says
  several calls arrive as separate assistant messages. vLLM's parser instead collects every
  complete call in the response into one `tool_calls` array. Run each call and send one tool
  message per `tool_call_id`.
- `tool_choice: "required"` or a named function is accepted but not enforced. The parser opts out
  (`supports_required_and_named = False`), so the request decodes like `"auto"` and the model may
  answer in prose. Check for `tool_calls` rather than assuming them.
- Each argument value is JSON-decoded on its own, whatever the schema says. A string parameter
  written as `123` arrives as the number 123, and `true` arrives as a boolean. Validate and coerce
  arguments against your schema before you use them.
- Use only letters, digits, `_`, `.` and `-` in tool names: the parser doesn't recognize a call
  addressed to any other name. A dot splits a namespace from a function (`calendar.create`).
- A call cut off by `max_tokens` is dropped, and the only trace is a warning in the server log.
  Treat `finish_reason: "length"` as a failed turn.
- vLLM v0.31.0 enforces no schema for Glimmer. Besides the forced tool choice above, a
  `response_format` JSON schema is silently skipped: the reasoning parser reports the end of
  reasoning only when a tool channel opens, so the grammar never reaches a plain answer
  (vllm#52594, open). With tools in the same request, the grammar switches on when the tool
  channel opens, so it constrains the tool call instead of the answer. Send no `response_format`.
  Offer the schema as a tool or describe it in the prompt, then validate and retry. In LangChain
  that means `ToolStrategy`, not `ProviderStrategy` (see
  [references/langchain.md](references/langchain.md)).

## 6. Prompts and images

- The template adds a knowledge-cutoff line (2026-01-04) and today's date only when the request
  has no system message. If you send your own system prompt, put the date in it.
- Images go in OpenAI `image_url` parts (an http(s) or `data:` URL), at up to 4,096 visual tokens
  per image. The model card lists text and image input only. Video isn't optimized for (it is
  processed as separate frames), and there is no audio.

## 7. Clients

- LangChain and Deep Agents: `ChatOpenAI` discards `reasoning`. Its own docs say non-standard
  provider fields are not extracted, so it can neither show the reasoning nor replay it. Use the
  `ChatMuseGlimmer` subclass in [references/langchain.md](references/langchain.md).
- Open WebUI and Claude Code: see [references/clients.md](references/clients.md). In short,
  Open WebUI needs `chat_template_kwargs` as a custom parameter, since its Reasoning Effort does
  nothing. Claude Code needs every model setting pointed at the served name and
  `ANTHROPIC_AUTH_TOKEN`, not `ANTHROPIC_API_KEY`, and only the server can set its reasoning
  strength.

## 8. Verify

Run the standard-library smoke test in [references/smoke-test.md](references/smoke-test.md)
against the server. It checks the served name, that `reasoning_strength` reaches the template
and `reasoning_effort` doesn't, which template the checkpoint ships, a tool call with its
reasoning replayed, and image input. Then confirm the sampling log line from section 3.

## Sources

Re-read these before you state a flag or default for a release newer than v0.31.0. Any
dev.meta.ai docs page is also served as Markdown: append `.md` to its URL.

- Meta: <https://dev.meta.ai/docs/muse-glimmer/vllm.md> and
  <https://dev.meta.ai/docs/muse-glimmer/prompting.md>. Meta's vLLM page names the recipe as its
  source of truth for flags and image tags.
- The vLLM recipe:
  <https://github.com/vllm-project/recipes/blob/main/models/meta-models/Muse-Glimmer-30B.yaml>
- The parsers at your release tag: `vllm/tool_parsers/muse_glimmer_tool_parser.py` and
  `vllm/reasoning/muse_glimmer_reasoning_parser.py` in `vllm-project/vllm`. For structured
  output, also `vllm/v1/structured_output/__init__.py` and issue vllm#52594.
- The model card, `generation_config.json` and `chat_template.jinja` of the checkpoint you serve.
