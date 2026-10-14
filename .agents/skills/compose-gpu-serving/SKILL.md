---
name: compose-gpu-serving
description: "Serve models on NVIDIA GPUs with Docker Compose (vLLM, llama.cpp, Ollama, SAM or any CUDA image): GPU reservations, healthchecks that wait out slow model loads, a shared Hugging Face cache, tokens from the environment, loopback-only ports, uv in images. Use when writing or fixing a compose.yaml that runs a GPU workload."
---

# Serving models with Docker Compose

A GPU service differs from an ordinary one in four ways: it needs the GPU passed in, it takes
minutes to become ready, it shares a scarce GPU and a large model cache with other services, and
it is often an unauthenticated API. Each section below handles one. For Compose and Dockerfile
basics use the `docker-compose-patterns` and `docker-build-strategies` skills; before any
command that deletes containers, images or volumes, use `docker-destructive-guardrails`.

## 1. Look before you change

- Read the existing `compose.yaml` (and any `compose.override.yaml`) and run
  `docker compose config` to see what Compose actually merges.
- Keep service, volume and project names. Compose names volumes `<project>_<volume>`, so a
  rename starts from an empty volume: a lost model cache means re-downloading tens of GB, and a
  lost database volume means lost data.
- Check the host: `nvidia-smi` (driver, and the highest CUDA version it supports),
  `docker compose version` (the `gpus:` key needs 2.30+), `nvidia-ctk --version`. NVIDIA
  Container Toolkit older than 1.17.8 has container-escape CVEs: tell the user; upgrading it is
  their call, not a step to take yourself.

## 2. Give the service a GPU

```yaml
services:
  vllm:
    gpus: all                      # Compose 2.30+; every GPU
    # or, for chosen GPUs (any Compose v2):
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           device_ids: ["0"]
    #           capabilities: [gpu]
```

Use device ids when models are pinned to different GPUs. Never use `privileged: true` to reach a
GPU. Check it worked: `docker compose exec vllm nvidia-smi`.

## 3. Wait for the model, not the process

The container starts in seconds; the model loads in minutes. Without a healthcheck, clients start
against a server that refuses connections.

```yaml
    healthcheck:
      # python, not curl: many inference images don't ship curl
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15m            # longer than the slowest load, download included
      start_interval: 10s          # poll often while loading (Compose 2.20.2+, Engine 25+)
```

Readiness endpoints: vLLM `GET /health`, llama.cpp `llama-server` `GET /health`, Ollama
`GET /` ("Ollama is running"). Clients wait with
`depends_on: {vllm: {condition: service_healthy}}`, and `docker compose up -d --wait` returns
only once everything is healthy.

## 4. Share the GPU deliberately

- vLLM takes `--gpu-memory-utilization` of the whole GPU at start (0.92 by default in v0.29
  to v0.31), whether it needs it or not. With other models on the same GPU, set it so the
  fractions add up to at most about 0.95, and cap `--max-model-len` so the KV cache fits. A
  SAM 3 service next to it needs roughly 4 to 8 GiB.
- PyTorch workers need shared memory: `shm_size: 16gb`. `ipc: host` also works but shares the
  host's IPC namespace; prefer `shm_size`.
- Measure, don't guess: `nvidia-smi` while every service is loaded and serving.

## 5. Models and tokens

```yaml
    environment:
      HF_TOKEN: ${HF_TOKEN:-}      # from the shell or a git-ignored .env; never written here
    volumes:
      - ${HOME}/.cache/huggingface:/root/.cache/huggingface
```

- Mount one host cache into every service that downloads from the Hub, so each model downloads
  once. After the first download, `HF_HUB_OFFLINE: "1"` stops the startup check against the Hub.
- Tokens come from the environment: `${VAR:-}` (optional) or `${VAR:?set VAR}` (required). Never
  put a token in `compose.yaml`, in a Dockerfile `ARG` or `ENV`, or in a committed `.env`; an
  `env_file` holding one is mode 600 and listed in `.gitignore`. Don't echo token values.

## 6. Who can reach it

- Publish on loopback: `ports: ["127.0.0.1:8000:8000"]`. A bare `"8000:8000"` listens on every
  interface, and Docker's port rules bypass the host firewall (ufw doesn't see them).
- Services reach each other by name on the Compose network (`http://vllm:8000/v1`), with no
  published port at all.
- Listen beyond loopback only on purpose, with an API key (`VLLM_API_KEY` or `--api-key` in
  vLLM). vLLM checks the key only on `/v1` routes; `/health`, `/metrics` and the rest stay
  open, so anything public goes behind a reverse proxy.

## 7. Images

- Pin images by digest, to the latest release at least 7 days old:
  `vllm/vllm-openai:<release>@sha256:<digest>`. `docker buildx imagetools inspect <image:tag>`
  prints the digest. Never `latest`.
- Building your own: pick a CUDA base the driver supports (`nvidia-smi` shows the highest CUDA
  version), and install Python dependencies with uv:

```dockerfile
FROM nvidia/cuda:<cuda>-runtime-ubuntu24.04
COPY --from=ghcr.io/astral-sh/uv:<uv-release> /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
CMD ["uv", "run", "--no-sync", "python", "-m", "app"]
```

  Run `docker build --check .` before building; it reports Dockerfile problems without building.

## 8. Keep heavy services opt-in

Put GPU services in a profile, so `docker compose up` on a machine without the GPU (a laptop,
CI) starts only the rest: `profiles: [gpu]`, then `docker compose --profile gpu up -d --wait`.
A service that `depends_on` a profiled one must be in the same profile.

## Check before you hand it back

```bash
docker compose config -q                          # valid, after interpolation
docker compose --profile gpu up -d --wait         # healthy, or it says which isn't
docker compose exec vllm nvidia-smi               # the GPU is visible inside
curl -fsS http://127.0.0.1:8000/v1/models         # serving (add -H "Authorization: Bearer ..." with a key)
docker compose logs -f vllm                       # watch a slow load
```

`docker compose down` keeps volumes. `down -v` deletes them, the model cache included; that is a
destructive command (see `docker-destructive-guardrails`).
