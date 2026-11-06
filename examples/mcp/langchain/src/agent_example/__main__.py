"""Run the example locally; Azure deployment remains an explicit operator operation."""

import argparse
import asyncio
import os

from langchain.chat_models import init_chat_model
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent_example.hosts import foundry_host, http_app
from agent_example.runtime import agent_runtime


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--host", choices=["local", "http", "responses", "invocations"], default="local"
    )
    parser.add_argument("--message", default="List available example records")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()
    model = init_chat_model(os.environ["AGENT_MODEL"])
    async with (
        AsyncSqliteSaver.from_conn_string(
            os.environ.get("CHECKPOINT_DB", "checkpoints.db")
        ) as saver,
        agent_runtime(os.environ["MCP_SERVER_URL"], model, saver) as graph,
    ):
        if args.host == "local":
            result = await graph.ainvoke(
                {"messages": [("user", args.message)]}, {"configurable": {"thread_id": "local"}}
            )
            print(result["messages"][-1].content)
        elif args.host == "http":
            import uvicorn

            await uvicorn.Server(
                uvicorn.Config(http_app(graph), host=args.bind, port=args.port)
            ).serve()
        else:
            await foundry_host(graph, protocol=args.host).run_async(host=args.bind, port=args.port)


if __name__ == "__main__":
    asyncio.run(main())
