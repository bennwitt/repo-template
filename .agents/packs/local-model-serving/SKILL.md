---
name: local-model-serving
description: "Serve local models on one NVIDIA GPU with vLLM, llama.cpp or Ollama: image pins, tool-call and reasoning parsers, Ampere quantization, sizing models that share a GPU, API keys, benchmarks, clients (LangChain, Claude Code). Use when choosing serve flags, pointing a client at a local model, or when tool calls or reasoning come back wrong."
---

# Serving local models

A local model server mostly fails without an error: tool calls arrive as plain text, reasoning
goes missing in the client, an FP8 checkpoint loads and runs no faster, a second model refuses
to start. This skill covers the choices behind those on one workstation GPU; an Ampere card such
as an RTX A6000 (48 GB) is the worked case. The container side (GPU reservations, healthchecks,
the shared Hugging Face cache, loopback ports, digest lookup) belongs to the
`compose-gpu-serving` skill: use it for the `compose.yaml`.

Facts here were checked on 2026-10-14 against vLLM v0.31.0, llama.cpp v0.6.0 and Ollama's docs.
After an upgrade, re-check anything tied to a version against that release's source.

## 1. Choose the server

- **vLLM** is the default: safetensors checkpoints (BF16, AWQ, GPTQ, FP8, INT8), many
  concurrent requests, OpenAI and Anthropic APIs (`/v1/chat/completions`, `/v1/messages`), and
  tool calls and reasoning parsed into their own fields. It reserves its memory share at start.
- **llama.cpp** (`llama-server`) for GGUF files, a model that fits only with some layers on the
  CPU, or a single user. It sizes itself to whatever memory is free when it starts.
- **Ollama** for trying models quickly. It loads and unloads models on demand, has no
  authentication, and gives the least control over memory and parsing.

Flags, pins and pitfalls for the last two: [references/llama-cpp-and-ollama.md](references/llama-cpp-and-ollama.md).

## 2. Pin vLLM to a release

- The newest release at least 7 days old on 2026-10-14 is v0.31.0 (published 2026-10-05):
  `vllm/vllm-openai:v0.31.0@sha256:c1c9f6fd5c109ba7f0546a59f5b2f15fb87f64c77782e90a27b648b42a8e67c3`.
  It is built on CUDA 13.0. When `nvidia-smi` reports a CUDA version below 13.0, use
  `vllm/vllm-openai:v0.31.0-cu129@sha256:ff29e51a9457f191deb332b96fa6440584fa941aa2a548449b604e2b1e5e1eeb`.
- To move on, list releases with
  `gh api repos/vllm-project/vllm/releases --jq '.[] | [.tag_name, .published_at] | @tsv'`,
  take the newest published at least 7 days ago, and read its "Breaking Changes" section first
  (v0.31.0 removed the AllSpark INT8 W8A16 backend and turned `quantization="fp8"` into
  `fp8_per_tensor`). Tags like `latest` and `nightly` move under you.
- Read docs for the pinned tag (`https://docs.vllm.ai/en/v0.31.0/`) and source at the tag
  (`https://raw.githubusercontent.com/vllm-project/vllm/v0.31.0/<path>`); flags and defaults
  change between releases.

## 3. Serve flags

Start from the model's recipe, `https://recipes.vllm.ai/<org>/<model>.json`: `features`
holds the tool-calling and reasoning flags, `variants` the quantized checkpoints with their VRAM
minimums (the `model-recipes` skill covers lookup). Keep its parser flags. Treat its hardware
tuning as unverified here: the recipe catalogue has no SM 8.0 or 8.6 profile. Do not copy its
`docker_command`: it runs with `--privileged` and `-p 8000:8000` (every interface), often names
`vllm/vllm-openai:latest`, and sometimes adds `--trust-remote-code`, which runs Python from the
model repo. Write the service with `compose-gpu-serving` and the pin instead.

Read parser names from the registries at the pinned tag, `vllm/tool_parsers/__init__.py` and
`vllm/reasoning/__init__.py`. At v0.31.0:

| Model | Flags |
| --- | --- |
| Qwen3 (Qwen3-14B, Qwen3-30B-A3B) | `--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3` |
| Qwen3.5, Qwen3.6 | `--enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3` |
| Qwen3-Coder | `--enable-auto-tool-choice --tool-call-parser qwen3_coder` (`qwen3_xml` is the same parser) |
| Muse Glimmer | `--enable-auto-tool-choice --tool-call-parser muse_glimmer --reasoning-parser muse_glimmer --generation-config auto` (vLLM 0.28.0 or later) |

For Muse Glimmer's sampling, reasoning strength and clients, use the `muse-glimmer` skill.

The other flags that decide behaviour:

- `--served-model-name qwen3-14b`: short, with no `/` (Claude Code cannot use a name containing
  one). It takes several names (`--served-model-name qwen3-14b Qwen/Qwen3-14B-AWQ`); responses
  report the first.
- `--max-model-len`: `32k` is 32,000 and `32K` is 32,768; `auto` picks the longest that fits.
  Cap it to what clients send: vLLM refuses to start when the KV cache cannot hold one sequence
  of that length, and long sequences crowd out concurrent ones. It also refuses a length above
  the model's own limit (`max_position_embeddings`; 40,960 for Qwen3-14B). Going past that
  needs the RoPE-scaling `--hf-overrides` from the recipe's `long_context` feature. Never set
  `VLLM_ALLOW_LONG_MAX_MODEL_LEN=1` to get round it: vLLM warns RoPE models then produce NaN.
- `--generation-config auto` (the default) applies the checkpoint's `generation_config.json`
  as default sampling. Quantized re-uploads can lose it: `RedHatAI/Muse-Glimmer-30B-FP8-block`
  has no sampling values, while `meta-models/Muse-Glimmer-30B` sets temperature 1.0, top_p
  0.95 and top_k 64. Compare the two files and restore the base values with
  `--override-generation-config '{"temperature": 1.0, "top_p": 0.95, "top_k": 64}'`, which
  merges with `auto`.
- Leave `--quantization` unset: vLLM reads the method from the checkpoint's config.
- `--default-chat-template-kwargs '{"enable_thinking": false}'` turns Qwen3 thinking off for
  every request; a request's own `chat_template_kwargs` still wins.

When output comes back wrong:

| Symptom | Cause |
| --- | --- |
| 400 `"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser` | neither flag is set |
| Tool-call JSON or XML inside `content`, no `tool_calls` | `--enable-auto-tool-choice` missing, or the wrong `--tool-call-parser` |
| `<think>` text inside `content` | no `--reasoning-parser` |
| Empty `content`, `finish_reason: "length"` | reasoning used up `max_tokens`: raise it, send `thinking_token_budget`, or turn thinking off |
| The client shows no reasoning | it reads `reasoning_content`, or it is LangChain `ChatOpenAI` (section 7) |
| 400 "maximum context length" | prompt tokens plus `max_tokens` exceed `--max-model-len` |
| 404 "model does not exist" | the request's `model` is not one of the served names |
| 401 | the key was not sent as `Authorization: Bearer` |

## 4. Quantization on Ampere

vLLM's v0.31.0 support table, for Ampere (SM 8.0 and 8.6): AWQ, GPTQ, Marlin (GPTQ, AWQ, FP8,
FP4), llm-compressor INT8 W8A8, bitsandbytes and GGUF are supported; llm-compressor FP8 W8A8 is
not.

- FP8 and NVFP4 checkpoints still load, but Ampere has no FP8 or FP4 math. vLLM runs them
  weight-only through Marlin (W8A16, W4A16) and logs "Your GPU does not have native support for
  FP8 computation ... Weight-only FP8 compression will be used leveraging the Marlin kernel"
  (FP4 likewise). They save memory, not compute, and the same log line warns "This may degrade
  performance for compute-heavy workloads."
- For speed on Ampere, use 4-bit AWQ or GPTQ (Marlin kernels) or INT8 W8A8.
- FP8 throughput figures from Ada, Hopper or Blackwell cards (recipes, model cards, blog posts)
  do not carry over. Measure on the card (section 8).
- `--kv-cache-dtype fp8` halves KV memory, but on Ampere at v0.31.0 the FlashAttention (FA2)
  and Triton backends reject an FP8 KV cache, which leaves FlashInfer. Check the
  `Using ... attention backend` log line and benchmark before keeping it.

## 5. Size models that share a GPU

- `--gpu-memory-utilization` (default 0.92 at v0.31.0) is this instance's fraction of the whole
  card. vLLM reserves it at start and fills whatever the weights leave with KV cache, needed or
  not. Every vLLM fraction, plus llama.cpp, Ollama, other GPU services and the desktop, has to
  fit in the card at once.
- vLLM refuses to start when the card's free memory is below its fraction ("Free memory on
  device ... is less than desired GPU memory utilization"). It also counts every allocation on
  the card between its own start and the end of its memory profiling as its own, so two
  instances loading at once shrink each other's KV cache or fail. Start them one after another
  (the healthcheck ordering is in `compose-gpu-serving`).
- Estimate before downloading with hf-mem 0.5.6 (released 2026-09-07; check
  `https://pypi.org/pypi/hf-mem/json` for a newer release at least 7 days old; the `hf-mem`
  skill covers its options):

  ```bash
  uvx hf-mem@0.5.6 --model-id Qwen/Qwen3-14B-AWQ --experimental \
    --max-model-len 32768 --kv-cache-dtype bfloat16
  ```

  `--experimental` adds the KV cache to the weights; `--batch-size N` sizes N full-length
  sequences at once. For a quantized checkpoint other than FP8, 0.5.6 stops with an error until
  you pass `--kv-cache-dtype`. Qwen3-14B-AWQ at 32,768 tokens comes out at 9.29 GiB of weights
  plus 5.00 GiB of KV cache per sequence. Activations, CUDA graphs and the CUDA context are not
  in the estimate, so leave headroom.
- The startup log is the ground truth: `Available KV cache memory: ... GiB` and
  `GPU KV cache size: ... tokens, Maximum concurrency for ... tokens per request: ...x`. Set the
  fraction from these, then confirm with `nvidia-smi` while every model is loaded and serving.
- `--kv-cache-memory-bytes` sets the KV cache size directly and ignores
  `--gpu-memory-utilization`: use it when a fixed budget per model matters more than automatic
  sizing.

## 6. Who can reach it

- `vllm serve` without `--host` listens on every interface (v0.31.0). On bare metal pass
  `--host 127.0.0.1`; in Docker publish the port on loopback (`compose-gpu-serving`).
- `--api-key`, or `VLLM_API_KEY` from the environment (a command line shows up in `ps`), checks
  only an `Authorization: Bearer` header, and only on paths under `/v1`, `/v2`, `/inference` and
  `/cohere`. Other routes stay open with a key set, including `/invocations` (the same inference
  as `/v1`), `/tokenize`, `/metrics` and `/health`, and with `VLLM_SERVER_DEV_MODE=1` also
  `/pause`, `/sleep` and `/collective_rpc`. vLLM's security docs say not to rely on the key
  alone: keep the port on loopback, or put a reverse proxy in front that passes only `/v1`.
  Leave `VLLM_SERVER_DEV_MODE` unset; vLLM logs it as a security warning.
- `--allowed-origins` defaults to `["*"]`, so a web page open in any browser on the machine can
  call the API. Set it to your front end's origin, as JSON:
  `--allowed-origins '["http://localhost:3000"]'`.
- llama-server checks its key on every route but `/health` and the web UI; Ollama has no
  authentication at all (see the reference).

## 7. Clients

- **Reasoning field.** vLLM returns `message.reasoning` (`delta.reasoning` when streaming). It
  used to be `reasoning_content`, and code that still reads the old name gets an empty value with
  no error. llama-server returns `reasoning_content`. Client code that may meet either reads
  `getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)`; the openai SDK
  exposes any extra response field as an attribute (checked with openai 3.26.0).
- **Thinking controls belong to the chat template.** vLLM passes `chat_template_kwargs` to the
  template, and a request's `reasoning_effort` goes in as a template variable that also sets
  `enable_thinking` (`"none"` turns it off, any other value on). A control works only if the
  template reads it: Qwen3's reads `enable_thinking` and not `reasoning_effort`, so effort levels
  only switch thinking on or off; Muse Glimmer's reads only `reasoning_strength`, so
  `reasoning_effort` does nothing there. Search the model's chat template for the variable first.
- **LangChain** `ChatOpenAI` drops `reasoning`, and **Claude Code** needs a launcher (served
  name without `/`, the key in `ANTHROPIC_AUTH_TOKEN`, context and output limits, a trimmed MCP
  set because tool search is off): [references/clients.md](references/clients.md).

## 8. Benchmark on this card

Run the benchmark client from the serving image, so vLLM never gets installed on the host.
`-e OPENAI_API_KEY` with no value copies it from your shell, so the key stays off the command
line:

```bash
OPENAI_API_KEY="$VLLM_API_KEY" docker exec -e OPENAI_API_KEY <container> vllm bench serve \
  --backend openai-chat --endpoint /v1/chat/completions \
  --model Qwen/Qwen3-14B-AWQ --served-model-name qwen3-14b \
  --dataset-name random --random-input-len 2048 --random-output-len 256 \
  --num-prompts 200 --max-concurrency 8 --save-result --result-dir /tmp/bench
docker cp <container>:/tmp/bench ./bench-results
```

`--model` names the tokenizer and `--served-model-name` is what the requests send. The client
sends `OPENAI_API_KEY` as the Bearer token, targets `127.0.0.1:8000` by default, and reaches
any other OpenAI-compatible server through `--base-url`. Results are written inside the
container, so copy them out before it is recreated. Change one thing per run (quantization,
`--max-num-seqs`, concurrency) and use the prompt lengths your clients send. Datasets, request
rates and the other options are in the `vllm-bench-serve` skill.

## Check before you hand it back

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS -H "Authorization: Bearer $VLLM_API_KEY" http://127.0.0.1:8000/v1/models   # served names; root is the checkpoint
docker compose logs vllm | grep -E 'attention backend|KV cache|Weight-only'
```

Then send one chat request with a `tools` list. Done means `tool_calls` is filled, `content`
holds no tool markup or `<think>` text, `reasoning` is non-empty for a reasoning model, and
`nvidia-smi` shows every co-resident model loaded with memory to spare.
