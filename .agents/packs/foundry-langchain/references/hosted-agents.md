# Hosting LangGraph and Deep Agents as Foundry hosted agents

This reference holds the detail behind section 6 of the skill. It was checked on 2026-10-14
against langchain-azure-ai 1.2.10, azd 1.35.0, the `azure.ai.agents` extension 1.0.0-beta.18,
and the Learn pages linked at the end. For the general azd workflow (provision, deploy, invoke,
logs, CI/CD), follow the `microsoft-foundry` skill. This file covers what is specific to
LangChain.

## Tooling

- azd must be 1.34.2 or later for extension 1.0.0-beta.18. Pin the extension:
  `azd extension install azure.ai.agents --version <version>`. Pick the newest release at least
  7 days old from the `azd-ext-azure-ai-agents_*` tags at
  https://github.com/Azure/azure-dev/releases. The `microsoft.foundry` meta-package pulls this
  extension in through a version range, so installing it does not pin `azure.ai.agents`. The
  pinned extension still installs its own dependencies (`azure.ai.projects`,
  `azure.ai.connections`, `azure.ai.toolboxes`, `azure.ai.inspector`) through version ranges.
- To make azd reuse the `az login` session, run `azd config set auth.useAzCliAuth true`.
- `azd ai agent run` (1.0.0-beta.18) installs the dependencies (`uv sync --locked` when
  `pyproject.toml` and `uv.lock` exist) and starts the agent directly, without Docker. Learn's
  statement that it builds the container image is out of date. It does not read
  `codeConfiguration.entryPoint`: pass `--start-command`, or set `startupCommand` in
  `azure.yaml`. In container mode, `azd deploy` builds the image remotely in Azure Container
  Registry unless `remoteBuild: false` is set, so you need local Docker only for a local build.

## Scaffolding

- `azd ai agent init -m <azure.yaml>` (1.0.0-beta.18) accepts only a **unified** `azure.yaml`:
  a `services` map with at least one `host: azure.ai.agent` service. It rejects standalone
  `agent.yaml` and `agent.manifest.yaml` files.
- Learn's hosting article points `-m` at
  `langchain-azure/samples/hosting/langgraph-hosted-agents/responses/01_basic/azure.yaml`. That
  folder has no `azure.yaml`, so the command fails. Start from one of the unified samples
  instead:
  - microsoft-foundry/foundry-samples, under `samples/python/hosted-agents/langgraph/`:
    `responses/10-run` (configuration-only), `responses/11-deep-agents`,
    `responses/08-observability`, `responses/07-human-in-the-loop`,
    `responses/02-langgraph-toolbox`, and `invocations/03-run`.
  - langchain-ai/langchain-azure: `responses/10_resilient` and `invocations/04_resilient`.
- To wrap existing code, run `azd ai agent init` in the project and let it write `azure.yaml`.
  It records the agent name, and reusing a name creates a new version of that agent rather than
  a new agent.

## The agent service in azure.yaml

azd generates the file. These are the fields you edit, as the configuration-only sample uses
them:

```yaml
  my-agent:
    host: azure.ai.agent
    kind: hosted
    name: my-agent
    project: src/my-agent
    language: python
    uses: [ai-project]
    codeConfiguration:
      runtime: python_3_13            # or python_3_14
      entryPoint: '-m langchain_azure_ai.agents.hosting.run --protocol responses'
    protocols:
      - protocol: responses
        version: 2.0.0
    env:
      AZURE_AI_MODEL_DEPLOYMENT_NAME: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
      TOOLBOX_NAME: my-tools
      LANGSMITH_TRACING: "true"
      LANGSMITH_API_KEY: ${{connections.<connection>.credentials.<field>}}
    container:
      resources: {cpu: "0.5", memory: 1Gi}
```

- `${VAR}` reads from the active azd environment (`.azure/<env>/.env`).
  `${{connections.<name>.<path>}}` is resolved by Foundry when the sandbox starts. Create the
  connection, for example a `CustomKeys` connection, before deploying. If it is missing, the
  variable starts empty.
- For a toolbox, add an `azure.ai.toolbox` service and list it under both `uses` and
  `toolboxes` on the agent. That only orders the deployment: the code still needs the toolbox
  name from `env`.
- `run.py` options: give the graph name as the first argument when `langgraph.json` defines
  several graphs, use `--config <path>` for a file elsewhere, and use
  `--option NAME=VALUE` for `ResponsesServerOptions` (for example
  `--option resilient_background=true`).

## Packaging traps

- **Code mode** (ZIP upload) is the default for Python. Packaging skips what `.agentignore`
  lists. With no `.agentignore`, the defaults exclude `.env`, `.env.*`, `.azure/`, `.git/` and
  `.venv/`. Writing an `.agentignore` replaces those defaults, so copy them into it or `.env`
  ships with the code. In `remote_build`, Learn documents dependency installation as pip
  reading `requirements.txt`. If a build fails or sticks in `creating` while resolving, export
  the lock with `uv export --frozen --no-dev --no-hashes --no-emit-project -o requirements.txt`,
  which also pins the content-understanding pre-release exactly. Learn's own fix for a stuck
  remote build is `dependencyResolution: bundled` with Linux wheels built locally.
- **Container mode**: list `.env` in `.dockerignore`. Build for `linux/amd64`, the only
  platform the runtime accepts (`docker build --platform linux/amd64 .` on ARM machines). For
  installing with uv in the image, follow the samples' `uv sync --frozen --no-dev` and the
  `docker-build-strategies` skill.
- Each `azd deploy` creates a new agent version. The endpoint follows the latest version unless
  you have pinned it.

## Conversations and state

- **Responses**: clients continue a conversation with `previous_response_id` or a
  `conversation` id. Reusing the same sandbox (its `$HOME` and uploaded files) needs
  `agent_session_id`, or a `conversation` id, which carries its own session.
- With a checkpointer, multi-turn needs an explicit `conversation.id` or
  `ResponsesServerOptions(steerable_conversations=True)`. Forking with `previous_response_id`
  alone is not supported for checkpointed graphs.
- **Invocations**: the platform stores no history. To keep using the same sandbox, send the
  `x-agent-session-id` response header back as the `agent_session_id` query parameter.
  Background turns need `InvocationsHostServer(graph, options=ResponsesServerOptions(
  resilient_background=True))` and a checkpointer; without them `"background": true` gets a
  400. With them it returns 202, and you poll `GET /invocations/{id}` for the result. `run.py`
  accepts `--option` only for Responses, so this needs a code host.
- **Human-in-the-loop** (needs a checkpointer): `interrupt()` comes back as a `function_call`
  item named `__hosted_agent_adapter_interrupt__` together with an `mcp_approval_request` whose
  `server_label` is `langgraph`. The client resumes with either a `function_call_output` whose
  `call_id` is the interrupt id (it carries a `Command` payload with `resume`, `update` or
  `goto`), or an `mcp_approval_response` whose `approval_request_id` is the interrupt id, for a
  plain approve or reject.
- `FoundryCheckpointSaver` keeps one state store per `thread_id`. It partitions by end user by
  default (`user_isolation=True`) and works only with `ainvoke` and `astream`: use it inside
  `async with`, then call `await ResponsesHostServer(graph).run_async()`. It needs the request
  context of a hosted agent, so local runs use `MemorySaver` or a database saver instead.

## Tracing

- The `responses/08-observability` sample calls `enable_auto_tracing()` inside the graph
  factory that `langgraph.json` points at, and sets `OTEL_AUTO_CONFIGURE_AZURE_MONITOR` and
  `AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED` to `'true'` in `azure.yaml` `env`. The second
  sends prompts, completions and tool arguments to App Insights; set it only if the user agrees.

## Deep Agents

- Pass the agent straight to the host: `ResponsesHostServer(create_deep_agent(...))`.
- `StateBackend` files live in the checkpoint, so they last only as long as the checkpointer.
  A `FilesystemBackend` under `$HOME` persists per session, across turns and idle periods, for
  up to 30 days. Sessions do not share it, so later turns need the same `agent_session_id` or
  `conversation` id.
- The `responses/11-deep-agents` sample combines `FoundryCheckpointSaver`, a toolbox (web
  search) and subagents.

## Local loop

```bash
uv run python -m langchain_azure_ai.agents.hosting.run --protocol responses --host 127.0.0.1
azd ai agent run --no-client \
  --start-command "python -m langchain_azure_ai.agents.hosting.run --protocol responses --host 127.0.0.1"
                                         # no Docker; sets PORT and FOUNDRY_PROJECT_ENDPOINT
azd ai agent invoke --local "Hello"
azd provision && azd deploy              # provision only when azure.yaml declares new resources
azd ai agent show                        # version, protocols, env
azd ai agent monitor                     # live container logs
```

## When it fails

| Symptom | Cause and fix |
|---|---|
| `424 session_not_ready` | `/readiness` did not return 200 in time. Read `azd ai agent monitor`, then fix startup: an import error, a missing env var, the wrong port. |
| Graph schema validation error | The state has no `messages` key. Override `build_input`, or `handle_create` for Responses. |
| The model is unreachable from the container | The deployment-name variable is missing from `env`, or an account-level call (embeddings, `[tools]` services) lacks a role for the agent identity. |
| `image_pull_failed` | The project's managed identity needs Container Registry Repository Reader on the registry, and the registry's `azureADAuthenticationAsArmPolicy` must be enabled. |
| `403` when invoking | The caller needs Foundry Agent Consumer (invoke only) or Foundry User on the project. |
| Conversation state resets | `MemorySaver`, or the client is not sending `conversation` / `previous_response_id`. |

## Sources

- https://learn.microsoft.com/azure/foundry/how-to/develop/langchain-hosted-agents
- https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent
- https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent-code
- https://learn.microsoft.com/azure/foundry/agents/how-to/author-azure-yaml
- https://learn.microsoft.com/azure/foundry/agents/how-to/manage-hosted-sessions
- https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions
- https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/langgraph
- https://github.com/langchain-ai/langchain-azure/tree/main/samples/hosting/langgraph-hosted-agents
