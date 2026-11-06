"""One graph, independent of transport, model provider and hosting environment."""

from langchain_core.messages import ToolMessage
from langgraph.func import task
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import interrupt


def build_graph(model, tools, checkpointer, *, write_tools=frozenset(), timeout=10):
    import asyncio

    by_name = {tool.name: tool for tool in tools}
    if len(by_name) != len(tools):
        raise ValueError("tool names must be unique across MCP servers")
    bound = model.bind_tools(tools)

    async def reason(state):
        async with asyncio.timeout(timeout):
            response = await bound.ainvoke(state["messages"])
        return {"messages": [response]}

    @task
    async def execute_one(call):
        name = call["name"]
        if name not in by_name:
            return ToolMessage("Unknown tool", tool_call_id=call["id"])
        if name in write_tools and interrupt({"tool": name, "args": call["args"]}) is not True:
            return ToolMessage("Write denied", tool_call_id=call["id"])
        try:
            async with asyncio.timeout(timeout):
                result = await by_name[name].ainvoke(call["args"])
            return ToolMessage(str(result), tool_call_id=call["id"])
        except (TimeoutError, RuntimeError, ValueError):
            return ToolMessage("Tool failed or timed out", tool_call_id=call["id"], status="error")

    async def execute(state):
        # Completed tasks are checkpointed across later interrupts in the same node.
        return {"messages": [await execute_one(call) for call in state["messages"][-1].tool_calls]}

    def route(state):
        return "tools" if state["messages"][-1].tool_calls else END

    graph = StateGraph(MessagesState)
    graph.add_node("model", reason)
    graph.add_node("tools", execute)
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", route)
    graph.add_edge("tools", "model")
    return graph.compile(checkpointer=checkpointer)
