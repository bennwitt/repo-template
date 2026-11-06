"""Thin local HTTP and Foundry hosts over the same compiled graph."""

from typing import Annotated

from fastapi import FastAPI, HTTPException, Request
from langgraph.types import Command
from pydantic import BaseModel, Field, StrictBool


class Turn(BaseModel):
    message: str
    thread_id: Annotated[str, Field(min_length=1, max_length=100)]


class Reply(BaseModel):
    message: str
    interrupted: bool


class Approval(BaseModel):
    thread_id: Annotated[str, Field(min_length=1, max_length=100)]
    approve: StrictBool


def http_app(graph, *, authorize_approval=None) -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ready"}

    @app.post("/invoke")
    async def invoke(turn: Turn) -> Reply:
        result = await graph.ainvoke(
            {"messages": [{"role": "user", "content": turn.message}]},
            {"configurable": {"thread_id": turn.thread_id}},
        )
        return Reply(
            message=str(result["messages"][-1].content),
            interrupted=bool(result.get("__interrupt__")),
        )

    @app.post("/resume")
    async def resume(approval: Approval, request: Request) -> Reply:
        # The host injects identity/thread authorization. The default host denies all writes.
        if authorize_approval is None or not await authorize_approval(request, approval.thread_id):
            raise HTTPException(
                status_code=403, detail="Approval requires authorized thread access"
            )
        result = await graph.ainvoke(
            Command(resume=approval.approve), {"configurable": {"thread_id": approval.thread_id}}
        )
        return Reply(
            message=str(result["messages"][-1].content),
            interrupted=bool(result.get("__interrupt__")),
        )

    return app


def foundry_host(graph, *, protocol="responses"):
    from langchain_azure_ai.agents.hosting import InvocationsHostServer, ResponsesHostServer

    if protocol == "responses":
        return ResponsesHostServer(graph)
    if protocol == "invocations":
        return InvocationsHostServer(graph)
    raise ValueError("protocol must be responses or invocations")
