"""The assistant loop: the model reads the snapshot, calls data tools when it needs more, then ends with `respond`."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from .providers import bind
from .tools import ALL_TOOLS, DATA_TOOLS, RESPOND, respond


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    steps: int
    final: dict[str, Any] | None


def build_graph(model: BaseChatModel, tool_choice: str = "any", max_steps: int = 4):
    # After max_steps lookups the model must answer with what it has: only `respond` is offered.
    with_tools = bind(model, ALL_TOOLS, tool_choice)
    respond_only = bind(model, [respond], tool_choice, force=RESPOND)

    async def agent(state: State, config: RunnableConfig) -> dict:
        runnable = respond_only if state["steps"] >= max_steps else with_tools
        message = await runnable.ainvoke(state["messages"], config)
        return {"messages": [message], "steps": state["steps"] + 1}

    def route(state: State) -> str:
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", None) or []
        if not calls or any(c["name"] == RESPOND for c in calls):
            return "finish"
        return "tools"

    def finish(state: State) -> dict:
        last = state["messages"][-1]
        call = next((c for c in (getattr(last, "tool_calls", None) or []) if c["name"] == RESPOND), None)
        if call:
            return {"final": dict(call["args"])}
        return {"final": {"reply": _text(last), "topic": "small_talk"}}

    graph = StateGraph(State)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(DATA_TOOLS))
    graph.add_node("finish", finish)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", "finish": "finish"})
    graph.add_edge("tools", "agent")
    graph.add_edge("finish", END)
    return graph.compile()


def _text(message: AIMessage) -> str:
    content = message.content
    if isinstance(content, list):  # some providers return content parts
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content).strip()
    return str(content or "").strip()
