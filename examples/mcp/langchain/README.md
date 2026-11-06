# Optional native LangChain MCP and portable graph

This isolated uv project demonstrates beta `langchain.mcp.MCPAdapter` with the same compiled
LangGraph behind local Python, FastAPI/Container Apps, Foundry Responses and Foundry Invocations.
It adds no runtime dependency to repo-template or unrelated generated repositories.

```bash
uv sync --locked --dev --python 3.12
LANGSMITH_TRACING=false uv run pytest
```

Tests use synthetic tools and deterministic model responses. HTTP and stdio tests need local
sockets/process IPC; restrictive agent sandboxes may require permission for those tests. No
cloud credentials or deployments are involved. Azure hosting is preview; two required Azure
preview dependencies are explicitly pinned. Other dependencies use ordinary release resolution.

`build_graph(model, tools, checkpointer)` injects the three runtime dependencies. The runtime
context holds MCP connections through the hosting lifespan. Unknown tools require approval by
default; server annotations never grant authorization. Explicitly classified read tools can run
without interruption. Checkpointed tool tasks avoid repeating completed calls when a later call
interrupts the same graph node. Production tools still need idempotency keys for crashes between
external side effects and checkpoint persistence.

For an interactive model, configure `AGENT_MODEL` using LangChain's provider-qualified syntax,
the provider's environment-based authentication, and `MCP_SERVER_URL`. Then run:

```bash
uv run python -m agent_example --host local --message 'Inspect example records'
uv run python -m agent_example --host http
uv run python -m agent_example --host responses
uv run python -m agent_example --host invocations
```

Provider extras may be needed for a selected model; add them to this example's environment with
uv. The graph itself has no Azure dependency. For a Foundry deployment, inject a model configured
for the project's deployed model and managed identity as described in the existing
`foundry-langchain` skill; that adapter does not change graph logic.

Local hosts bind to loopback. The container binds to its internal interface; publish only a
loopback host port for local Docker testing. The Dockerfile runs as a non-root user and excludes
credentials from its build context. The sample `azure.yaml` identifies a hosted-agent entrypoint;
populate the project, model and runtime MCP environment for the intended Azure target using the
current azd workflow. The equivalent Container Apps deployment uses the same image with `--host
http --bind 0.0.0.0`. Add authenticated ingress and identity-bound thread authorization before
exposing the example to other users.

SQLite checkpoints demonstrate local persistence. Use an appropriate durable shared store for
multi-instance hosting; neither container-local SQLite nor an in-memory checkpointer provides
that guarantee. The HTTP example's `/resume` endpoint denies access unless the host injects
`authorize_approval(request, thread_id)`. That callback must authenticate the approver and authorize
the specific thread; a boolean payload alone grants nothing. Foundry Responses continues with
`previous_response_id`; Invocations reuses the `x-agent-session-id` response header as the
`agent_session_id` query parameter. Both accept interrupt-matched `function_call_output` items
containing a JSON `resume` decision. Tests exercise continuation and approval through all hosts.

The sibling `legacy-langchain` project locks the old adapter and MCP v1 separately. Its stdio
fixture protects legacy consumers; selecting native MCP does not migrate their dependencies.

Sources: [native MCP](https://docs.langchain.com/oss/python/langchain/mcp),
[Foundry hosting](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/langchain-hosted-agents).
