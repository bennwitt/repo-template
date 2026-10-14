---
name: foundry-langchain
description: "LangChain, LangGraph and Deep Agents on Microsoft Foundry with langchain-azure-ai: keyless Foundry models through DefaultAzureCredential, Azure Monitor tracing beside LangSmith, Foundry Toolbox tools, and hosting a graph as a Foundry hosted agent with azd. Use when a LangChain or LangGraph project calls Foundry models or deploys to Foundry."
---

# LangChain on Microsoft Foundry

Foundry changes four things in a LangChain project. Models authenticate with Entra ID against
a **project endpoint** instead of an API key. Traces gain a second sink, Azure Monitor, next to
LangSmith. Tools can come from a Foundry Toolbox over MCP. A graph can run as a **hosted agent**
with its own identity, injected environment and state. The integration package is
`langchain-azure-ai`, which is Python only. The facts below were checked on 2026-10-14 against
langchain-azure-ai 1.2.10, azure-identity 1.26.0, uv 0.12.23, azd 1.35.0 with the
`azure.ai.agents` extension 1.0.0-beta.18, and Microsoft Learn.

Other skills cover the neighbouring work: `microsoft-foundry` for azd provisioning, deploying,
invoking and troubleshooting agents; `langgraph-persistence` for checkpointers;
`langgraph-human-in-the-loop` for interrupts; `deep-agents-core` and `deep-agents-memory` for
Deep Agents; `langchain-middleware` for approval middleware. For any API signature not given
here, query the Learn MCP (`microsoft_docs_search`) or read the installed package's source.
Memory is not a source.

## 1. Look before you change

- Read `pyproject.toml` and `uv.lock`, plus `azure.yaml`, `langgraph.json` and `.env.example` if
  they exist. List the environment variable names the code actually reads.
- `az account show` confirms the sign-in. Subscription and tenant ids stay in the az and azd
  stores (`~/.azure`, `.azure/<env>/.env`). Never copy them into code, `.env.example`,
  `azure.yaml` or docs: code needs only the project endpoint.
- `git check-ignore .env .azure/` must print both paths. Keep the trailing slash: without it,
  git reports nothing for `.azure` until the directory exists. If either is missing, add it to
  `.gitignore` first. `.azure/<env>/.env` holds the azd environment, including any secret set
  with `azd env set`.

## 2. Install

| Need | Install |
|---|---|
| Chat and embedding models, Agent Service nodes | `langchain-azure-ai` |
| Azure Monitor tracing | `langchain-azure-ai[opentelemetry]` |
| Hosting as a Foundry hosted agent | `langchain-azure-ai[hosting]` |
| Document Intelligence, Speech, Logic Apps and other service tools | `langchain-azure-ai[tools]` |
| Foundry Toolbox | `langchain-mcp-adapters` and `httpx` (no extra installs them) |
| Foundry classic (deprecated inference classes) | `langchain-azure-ai[v1]` |

- langchain-azure-ai 1.2.10 needs Python 3.11 or later. Learn pages still say 3.10.
- 1.2.10 depends on `azure-ai-contentunderstanding>=1.2.0b2`, which has no final release yet.
  uv 0.12 and later fall back to that pre-release by themselves, so
  `uv add 'langchain-azure-ai[hosting,opentelemetry]==1.2.10'` resolves. uv 0.11 and earlier
  refuse a pre-release that only a dependency asks for; there, also add
  `'azure-ai-contentunderstanding==1.2.0b3'`, or upgrade uv. Check with `uv --version`.
- The official Foundry samples set `prerelease = "allow"` in `uv.toml`, which lets every package
  float to pre-releases. Don't copy it.
- Pin each package to its newest release at least 7 days old. Check upload dates with
  `curl -s https://pypi.org/pypi/<package>/json`, and hold the whole lock back with
  `uv lock --exclude-newer "7 days"`.

## 3. Models, keyless

```python
from langchain.chat_models import init_chat_model

model = init_chat_model("azure_ai:<deployment-name>")   # DefaultAzureCredential, Responses API
```

The explicit form, for when you need to pass the endpoint or the credential:

```python
import os
from azure.identity import DefaultAzureCredential
from langchain_azure_ai.chat_models import AzureAIOpenAIApiChatModel

model = AzureAIOpenAIApiChatModel(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
    model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
)
```

- `model` is the **deployment** name, which can differ from the base model's name. Deep Agents
  accepts the same string (`create_deep_agent(model="azure_ai:<deployment-name>")`).
- Use these classes rather than a hand-built `ChatOpenAI`. They wire the token provider into
  both the sync and async clients, and they add the `type: "message"` field that Foundry's
  Responses API requires on input items (per the 1.2.10 source). Existing code that builds
  `ChatOpenAI` from `AIProjectClient.get_openai_client()`, as Learn and the samples do, works,
  so leave it alone unless asked.
- Endpoint resolution order: constructor argument, then `AZURE_AI_PROJECT_ENDPOINT`, then
  `FOUNDRY_PROJECT_ENDPOINT`, then `AZURE_AI_OPENAI_ENDPOINT`, then `AZURE_OPENAI_ENDPOINT`.
  `AZURE_AI_PROJECT_ENDPOINT` wins silently, so a stale value in `.env` or in `azure.yaml` sends
  a hosted agent to the wrong project. The toolbox and the tracers resolve the endpoint the same
  way. Hosted code should pass `FOUNDRY_PROJECT_ENDPOINT` explicitly.
- Roles: whoever calls the project endpoint needs **Foundry User** (formerly Azure AI User) on
  the project. Owner and Contributor are control-plane roles and cannot call models.
- **Embeddings** are the exception. With a token credential, `AzureAIOpenAIApiEmbeddingsModel`
  calls the account's `https://<resource>.services.ai.azure.com/openai/v1`, not the project,
  because 1.2.10 cannot route embeddings through the project endpoint. That is account scope:
  the calling identity needs Cognitive Services OpenAI User or Foundry User on the Foundry
  account. This includes a hosted agent's identity, which by default can only call models
  through the project endpoint. The project endpoint does not proxy Speech, Document
  Intelligence or Content Safety either, the services behind the `[tools]` classes and the
  content-safety middleware, so those need Cognitive Services User or Foundry User on the
  account.
- API keys work only against the direct endpoint (`endpoint=".../openai/v1"`,
  `credential=<key>`). Use a key only as a fallback: read it from the environment and never
  commit it.
- In azure-identity 1.26.0, `DefaultAzureCredential` tries an environment service principal
  first, then workload identity, then managed identity, and reaches the Azure CLI only after
  those. A service principal left in `.env` (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`,
  `AZURE_CLIENT_SECRET`) therefore silently wins over `az login`. On a dev machine, put
  `AZURE_TOKEN_CREDENTIALS=AzureCliCredential` (or `dev`) in `.env` to pin the chain. Leave it
  unset in Azure.

## 4. Tracing: Azure Monitor beside LangSmith

Both sinks are LangChain callback handlers, so they can run together. LangSmith needs only
environment variables: `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, and
`LANGSMITH_ENDPOINT` for non-US regions. It sends from a background thread, so short scripts
should call `wait_for_all_tracers()` (from `langchain_core.tracers.langchain`) before exiting.
LangSmith stores full inputs and outputs unless `LANGSMITH_HIDE_INPUTS=true` and
`LANGSMITH_HIDE_OUTPUTS=true` are set; ask before sending production data there.

Azure Monitor needs the `[opentelemetry]` extra:

```python
from langchain_azure_ai.callbacks.tracers import enable_auto_tracing

enable_auto_tracing(auto_configure_azure_monitor=True)   # every callback manager gets the tracer
```

Alternatively, attach `AzureAIOpenTelemetryTracer(...)` to one runnable with
`.with_config({"callbacks": [tracer]})`.

- **Content recording has opposite defaults.** `AzureAIOpenTelemetryTracer(...)` records
  prompts, completions and tool arguments by default (`enable_content_recording=True`).
  `enable_auto_tracing` does not, unless `AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED=true`.
  Set it explicitly either way: anyone who can read the traces (Monitoring Reader on App
  Insights, Log Analytics Reader on its workspace) can read recorded content.
- **Exporter setup has opposite defaults too.** The tracer class configures Azure Monitor when
  it finds a connection string. `enable_auto_tracing()` does not, unless you pass
  `auto_configure_azure_monitor=True` or set `OTEL_AUTO_CONFIGURE_AZURE_MONITOR=true`; otherwise
  a local run exports nothing. If a TracerProvider already exists, the tracer emits through it
  and does not configure a second one.
- Both read only `APPLICATION_INSIGHTS_CONNECTION_STRING`, spelled with an underscore, never the
  `APPLICATIONINSIGHTS_CONNECTION_STRING` that Azure Monitor and the hosted platform use.
  Without it, they look up the App Insights resource connected to the project, given a project
  endpoint (`enable_auto_tracing` reads one from the environment; `AzureAIOpenTelemetryTracer`
  only uses one passed to it). Keep the connection string in `.env`, never in committed files.
- In a hosted agent, the platform injects `APPLICATIONINSIGHTS_CONNECTION_STRING` and the agent
  server exports its per-request span there. Follow the upstream observability sample (see
  [references/hosted-agents.md](references/hosted-agents.md)), but not its content-recording
  setting: decide that with the user. After the first deploy, check App Insights once for
  duplicate spans.

## 5. Foundry Toolbox

```python
from langchain_azure_ai.tools import AzureAIProjectToolbox

toolbox = AzureAIProjectToolbox(toolbox_name=os.environ["TOOLBOX_NAME"])  # endpoint from env
tools = await toolbox.get_tools()                  # a coroutine in 1.2.10, despite the name
needs_approval = await toolbox.get_tools_requiring_approval()
```

- `AzureAIProjectToolbox` is a preview class: it emits an `ExperimentalWarning` and sends
  `Foundry-Features: Toolboxes=V1Preview`. No environment variable supplies the toolbox name, so
  declare your own (such as `TOOLBOX_NAME`) in `azure.yaml` `env`.
- A tool configured with `require_approval: always` is gated by neither LangChain nor the
  toolbox endpoint, which does not block the call; it runs like any other tool. To gate it, add
  `HumanInTheLoopMiddleware(interrupt_on={name: True for name in needs_approval})` to the agent,
  which also needs a checkpointer (see `langchain-middleware`).
- If the toolbox still needs OAuth consent, `get_tools()` returns a single fallback tool, in
  place of all the toolbox's tools, that hands the consent URL to the user. Once the user has
  consented, restart the agent.
- Each `get_tools()` call opens a new MCP session, so load the tools once at startup.
- For Deep Agents, `toolbox.get_skills()` returns a files mapping. Create the agent with
  `skills=["/skills/"]` and pass the mapping as `files` on invoke, or write it into a backend
  with `await toolbox.aget_skills(backend=...)`.
- In a hosted agent, the per-call `x-agent-foundry-call-id` header is forwarded automatically
  (1.2.8 and later).

## 6. Hosting as a Foundry hosted agent

Learn documents hosted agents for Python and .NET only; there is no Node.js runtime. The calls
to make:

- **Prefer configuration-only hosting.** Make the container entry point
  `python -m langchain_azure_ai.agents.hosting.run --protocol responses`. It loads the graph
  from `langgraph.json` and serves on `$PORT` (8088 by default), so a project that already runs
  under the LangGraph CLI needs no code changes. It reads only `graphs` from that file, not
  `env`, so load `.env` in code for local runs (the samples call `load_dotenv()`). Write a
  `ResponsesHostServer(graph)` host only when you need custom request handling.
- **Bind local runs to loopback.** `run.py`, `ResponsesHostServer.run()` and `run_async()` bind
  `0.0.0.0` by default, and the local server has no inbound auth: anyone on the network could
  call your models and tools with your credentials. Locally, pass `--host 127.0.0.1` (or
  `host="127.0.0.1"`). Keep the default in the deployed entry point, where the platform routes
  traffic to the container.
- **Choose the protocol.** Responses suits chat: the platform keeps the history and
  conversations. Invocations suits custom JSON and webhooks, and your code keeps all state.
- The default hosts expect a `messages` key in the graph state. For any other state shape,
  subclass the host and override `build_input`.
- **State.** Without a checkpointer, the host replays the platform's Responses history. With
  one, it sends only the current input and the checkpointer holds the state. `MemorySaver`
  loses everything when compute idles out (after 15 minutes by default), so production needs a
  durable checkpointer: `FoundryCheckpointSaver` (async only, 30-day sliding TTL, works only
  inside a hosted agent, so use `MemorySaver` or a database saver locally) or your own database
  saver. Leave an existing checkpointer in place unless the user asks to change it.
- **Identity.** The container runs as the agent's own Entra identity, created at deploy time,
  and `DefaultAzureCredential` picks it up. By default it can call models through the project
  endpoint and use session storage. Anything else (account-level embeddings, Storage, AI
  Search, Key Vault) needs a role assigned to that identity. Deploying requires
  **Foundry Project Manager** on the project.
- **Environment.** The platform injects `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_AGENT_NAME`,
  `FOUNDRY_AGENT_VERSION` and `APPLICATIONINSIGHTS_CONNECTION_STRING`. The `FOUNDRY_` prefix is
  reserved, so never redeclare those variables. The model deployment name is not on the
  platform's injected list: declare it in `azure.yaml` `env`, and read whatever name that file
  declares. The docs disagree on the name; extension 1.0.0-beta.18 writes
  `AZURE_AI_MODEL_DEPLOYMENT_NAME` to the azd environment.
- **Secrets** reach the container as connection placeholders in `azure.yaml` `env`, for
  example `LANGSMITH_API_KEY: ${{connections.<connection>.credentials.<field>}}`. Never put a
  secret value in `azure.yaml` or in the image.

The azd flow, `azure.yaml`, packaging traps, conversation threading, human-in-the-loop over
Responses, Deep Agents state and the failure modes are in
[references/hosted-agents.md](references/hosted-agents.md). Read it before scaffolding,
deploying or debugging a hosted agent.

## 7. TypeScript

There is no langchain-azure-ai for JavaScript, and `@langchain/azure-openai` is deprecated on
npm. Use `@langchain/openai` instead: in 1.6.2, `AzureChatOpenAI` takes an
`azureADTokenProvider` for keyless auth. Run TypeScript agents somewhere other than Foundry
hosted agents, for example Container Apps.

## Check before you hand it back

```bash
git check-ignore .env .azure/                    # both printed: neither can be committed
uv run python -m langchain_azure_ai.agents.hosting.run --protocol responses --host 127.0.0.1
curl -sS -X POST http://127.0.0.1:8088/responses \
  -H 'Content-Type: application/json' -d '{"input":"Hello","stream":false}'
azd ai agent run --no-client \
  --start-command "python -m langchain_azure_ai.agents.hosting.run --protocol responses --host 127.0.0.1"
azd ai agent invoke --local "Hello"
```

- `azd ai agent run` ignores `codeConfiguration.entryPoint` and otherwise guesses
  `python main.py`, hence `--start-command` (or `startupCommand` in `azure.yaml`).
- Search the changes for API keys, connection strings, subscription or tenant ids and
  `api_key=` literals. None of them belong in code, `azure.yaml`, `.env.example` or docs.
- If tracing was in scope, invoke once and confirm the spans arrive in App Insights and, if it
  is configured, in LangSmith.
