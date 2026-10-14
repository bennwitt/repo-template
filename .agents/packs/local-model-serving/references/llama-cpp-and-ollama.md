# llama.cpp and Ollama

Checked on 2026-10-14 against llama.cpp v0.6.0 (released 2026-10-05: `docs/build.md`,
`tools/server/README.md`, `.devops/cuda.Dockerfile`) and Ollama's docs
(`https://docs.ollama.com/llms.txt` indexes them as Markdown). Compose wiring for either is in
the `compose-gpu-serving` skill; finding a GGUF and choosing its quant is in
`huggingface-local-models`.

## llama.cpp `llama-server`

### Build or pull

```bash
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86   # 86: RTX 30xx, RTX A-series; A100 is 80
cmake --build build --config Release -j "$(nproc)"
```

- A plain build targets the GPU it can see. Where none is visible, nvcc warns
  `Cannot find valid GPU for '-arch=native'` and uses a default architecture, so name it.
- The repo's Docker build turns native detection off and compiles every supported
  architecture. For Ampere only (a faster build, a smaller image):

  ```bash
  docker build -t local/llama.cpp:server-cuda --target server \
    --build-arg CUDA_DOCKER_ARCH=86 -f .devops/cuda.Dockerfile .
  ```

- Prebuilt images: `ghcr.io/ggml-org/llama.cpp:server-cuda` (CUDA 12.8.1 base) and
  `:server-cuda13` (CUDA 13.4.1 base). They are built nightly, so versioned tags exist for some
  builds only, and v0.6.0 has none of its own. On 2026-10-14:
  - the newest release image at least 7 days old is
    `ghcr.io/ggml-org/llama.cpp:server-cuda-v0.5.0@sha256:52192a23c7b258044463aebba78826cdff39a7393b713edc313324b343a7b836`
    (v0.5.0, 2026-09-23); the flags below are the same there;
  - for v0.6.0 itself, run the build above in a checkout of the tag
    (`git clone --depth 1 --branch v0.6.0 https://github.com/ggml-org/llama.cpp`);
  - `server-cuda-b<build>` tags are CI builds that GitHub marks as pre-releases. The closest
    after v0.6.0 is `server-cuda-b11459@sha256:fff6185edd2fbc4093aa5970bf6db53ed11c283e3a1c52a3e244cf27047264f4`
    (2026-10-07).

  To move on, list `v*` releases with `gh api repos/ggml-org/llama.cpp/releases`, then check
  the image exists and read its digest with
  `docker buildx imagetools inspect ghcr.io/ggml-org/llama.cpp:server-cuda-v<version>`.

### Flags that matter (v0.6.0; `--help` shows each one's environment variable)

- `-hf <user>/<repo>[:quant]` downloads a GGUF from the Hub (quant defaults to `Q4_K_M`); `-m`
  takes a local file. `--alias` sets the model name the API reports.
- `-c` defaults to 0, meaning the model's trained context. `--fit` is on by default and shrinks
  any setting you left unset (context, GPU layers) to fit the memory free at start, keeping
  1024 MiB per device (`--fit-target`) and at least 4096 tokens of context (`--fit-ctx`). Next
  to vLLM, start llama-server after vLLM has loaded, or set `-c` and `-ngl` yourself; otherwise
  it takes memory vLLM expects, or quietly runs with a smaller context.
- `-ngl` defaults to `auto`; `all` keeps every layer on the GPU.
- `-np` (slots) defaults to auto, and then one KV buffer is shared across slots (`--kv-unified`).
- `--jinja` is on by default: the chat template comes from the GGUF, and tool calls need it.
  `Chat format: Generic` in the log means no native handler matched the template: tool calls
  still work, less efficiently, and `--chat-template-file` can supply a better template.
- `--reasoning-format` defaults to `auto`; reasoning arrives in `message.reasoning_content`,
  not vLLM's `reasoning`.

### Exposure

- The binary listens on `127.0.0.1:8080`; the server image sets `LLAMA_ARG_HOST=0.0.0.0`, so
  publish its port on loopback.
- `--api-key` (or `LLAMA_API_KEY`, or `--api-key-file`) is checked on every route except
  `/health`, `/v1/health` and the web UI, as `Authorization: Bearer` or `X-Api-Key`.
- By default the server reflects any `Origin` back with credentials allowed. Set
  `--cors-origins localhost` (or your front end's origin) when browsers are involved.
- `--tools` and `--agent` (experimental, off by default) give the API built-in tools that read
  and write files and run shell commands on the host. Leave them off on anything reachable by
  others.

## Ollama

- Pin the image to a release at least 7 days old, by digest: `ollama/ollama:<version>@sha256:...`
  (releases: `gh api repos/ollama/ollama/releases`).
- It listens on `127.0.0.1:11434`; the image sets `OLLAMA_HOST=0.0.0.0:11434`, so publish on
  loopback. There is no authentication: the OpenAI SDK needs some `api_key`, and Ollama
  ignores it.
- OpenAI-compatible API at `http://127.0.0.1:11434/v1`. `tool_choice` is not supported, images
  go in as base64 (not URLs), and `reasoning_effort` maps to each model's own levels
  (`/api/show` lists them). It also serves the Anthropic API for Claude Code.
- **Context.** The Context length page sets the default by VRAM (4k under 24 GiB, 32k from 24
  to 48 GiB, 256k at 48 GiB and above) while the FAQ still says 4096. Do not predict it: read
  the `CONTEXT` column of `ollama ps`, and set `OLLAMA_CONTEXT_LENGTH` yourself. Memory grows
  with `OLLAMA_NUM_PARALLEL` times the context. The OpenAI API cannot set context; a Modelfile
  with `PARAMETER num_ctx <n>` can.
- **Memory.** Ollama loads a model on its first request into whatever memory is free, keeps it
  for 5 minutes (`OLLAMA_KEEP_ALIVE`, or `keep_alive` per request), and holds up to
  `OLLAMA_MAX_LOADED_MODELS` (default 3 per GPU). Next to vLLM it may split a model onto the CPU
  without failing: the `PROCESSOR` column of `ollama ps` should read `100% GPU`. The KV cache
  is `f16` unless `OLLAMA_KV_CACHE_TYPE` says otherwise.
