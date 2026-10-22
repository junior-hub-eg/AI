"""The assistant loop: the model reads the snapshot, calls data tools when it needs more, then ends with `respond`."""

from __future__ import annotations

import re
from typing import Annotated, Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage
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


def build_graph(model: BaseChatModel, tool_choice: str = "any", max_steps: int = 4, fallback: BaseChatModel | None = None):
    # After max_steps lookups the model must answer with what it has: only `respond` is offered.
    with_tools = bind(model, ALL_TOOLS, tool_choice)
    respond_only = bind(model, [respond], tool_choice, force=RESPOND)
    backup = (bind(fallback, ALL_TOOLS, tool_choice), bind(fallback, [respond], tool_choice, force=RESPOND)) if fallback else None

    async def agent(state: State, config: RunnableConfig) -> dict:
        last_step = state["steps"] >= max_steps
        runnable = respond_only if last_step else with_tools
        try:
            try:
                message = await runnable.ainvoke(state["messages"], config)
            except Exception as exc:
                if not (backup and rate_limited(exc)):
                    raise
                # The main model's quota is used up: this step goes to the fallback model, with its own quota.
                runnable = backup[1] if last_step else backup[0]
                message = await runnable.ainvoke(state["messages"], config)
        except Exception as exc:
            if not tool_use_failed(exc):
                raise
            # The model wrote a tool call the provider rejected (Groq's tool_use_failed, frequent with gpt-oss):
            # try once more, then ask for a plain-text answer, which `finish` accepts as the reply.
            try:
                message = await runnable.ainvoke(state["messages"], config)
            except Exception as again:
                if not tool_use_failed(again):
                    raise
                message = await model.ainvoke([*state["messages"], SystemMessage(PLAIN_ANSWER)], config)
                message = AIMessage(content=_text(message))  # no tool calls: the loop finishes with this text
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
        return {"final": split_plain_reply(_text(last))}

    graph = StateGraph(State)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(DATA_TOOLS))
    graph.add_node("finish", finish)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", "finish": "finish"})
    graph.add_edge("tools", "agent")
    graph.add_edge("finish", END)
    return graph.compile()


PLAIN_ANSWER = (
    "Answer the student now in plain text, without calling any tool, using only the data you already have. "
    "Follow all the rules above."
)


# A plain-text answer sometimes copies the fields of `respond` at its end ("**اقتراحات:**", "Topic: learning",
# "Links: [...]"). Those lines start the part that is not for the student.
_META_START = re.compile(
    r"^[\s*_#>-]*(اقتراحات|اقتراح|أسئلة مقترحة|الموضوع|الروابط|روابط|suggestions?|topic|links?)(?:\s+[^\s:：*]+){0,2}\s*[*_]*\s*[:：]",
    re.IGNORECASE,
)
_SUGGESTION_HEAD = re.compile(r"(اقتراح|أسئلة|suggest)", re.IGNORECASE)
_TOPIC_HEAD = re.compile(r"(الموضوع|topic)", re.IGNORECASE)
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*\S)\s*$")


def split_plain_reply(text: str) -> dict[str, Any]:
    """The reply of a plain-text answer, with the suggestions and topic it wrote at its end taken out of it."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if _META_START.match(line)), len(lines))
    reply = "\n".join(lines[:start]).strip() or text.strip()
    suggestions: list[str] = []
    topic = "small_talk"
    section = ""
    for line in lines[start:]:
        if head := _META_START.match(line):
            section = "suggestions" if _SUGGESTION_HEAD.search(head.group(1)) else (
                "topic" if _TOPIC_HEAD.search(head.group(1)) else "other")
            rest = line[head.end():].strip(" *_`")
            if section == "topic" and rest:
                topic = rest.split()[0].strip("*_`.,").lower()
            continue
        if section == "suggestions" and (bullet := _BULLET.match(line)):
            suggestions.append(bullet.group(1).strip(" *_`\"“”"))
    return {"reply": reply, "topic": topic, "suggestions": suggestions[:3]}


def rate_limited(exc: Exception) -> bool:
    """The provider refused the call for quota (HTTP 429)."""
    return getattr(exc, "status_code", None) == 429 or type(exc).__name__ == "RateLimitError"


def tool_use_failed(exc: Exception) -> bool:
    """The provider refused the model's own tool call (Groq: status 400, code tool_use_failed)."""
    body = getattr(exc, "body", None)
    inner = body.get("error", body) if isinstance(body, dict) else None
    code = inner.get("code") if isinstance(inner, dict) else None
    return code == "tool_use_failed" or "tool_use_failed" in str(exc)


def _text(message: AIMessage) -> str:
    content = message.content
    if isinstance(content, list):  # some providers return content parts
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content).strip()
    return str(content or "").strip()
