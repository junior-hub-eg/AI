"""Turns one request into one reply: builds the messages, runs the graph, and cleans the result."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .catalog import Catalog, load_catalog
from .config import Settings
from .graph import build_graph
from .prompt import PROMPT_VERSION, SYSTEM_PROMPT, snapshot
from .schemas import MAX_REPLY, MAX_SUGGESTION, Link, Meta, ReplyRequest, ReplyResponse

PAGE_KINDS = {"squad", "discovery", "achievements", "jobs"}
TOPICS = set(ReplyResponse.model_fields["topic"].annotation.__args__)


# Citation tags some models put in their text, e.g. Cohere's "<co>3 lessons</co: 0:[0]>" or "<co: 0>".
CITATION_TAGS = re.compile(r"</?co(?:\s*:[^>]*)?>")


def strip_markup(text: str) -> str:
    # Only the tags go; spacing is kept as written (code in a reply keeps its indentation).
    return CITATION_TAGS.sub("", text).strip()


def _parsed(content):
    try:
        return json.loads(content)
    except (TypeError, ValueError):
        return content


class EmptyReply(Exception):
    """The model finished without anything to say."""


@dataclass
class Assistant:
    model: BaseChatModel
    settings: Settings
    catalog: Catalog = field(default_factory=load_catalog)

    def __post_init__(self) -> None:
        self.graph = build_graph(self.model, self.settings.llm_tool_choice, self.settings.max_steps)

    async def reply(self, request: ReplyRequest) -> tuple[ReplyResponse, list[str]]:
        """The reply, and the names of the tools used (for logs and the CLI)."""
        response, trace = await self.reply_with_trace(request)
        return response, [step["tool"] for step in trace["steps"]]

    async def reply_with_trace(self, request: ReplyRequest) -> tuple[ReplyResponse, dict]:
        """The reply, and what the model saw: the student snapshot and every tool call with its arguments and the
        data it returned. For checking replies against the data (dev endpoints only, never logged)."""
        started = time.perf_counter()
        ctx = request.context
        messages = [SystemMessage(f"{SYSTEM_PROMPT}\nStudent snapshot:\n{snapshot(ctx, self.catalog)}")]
        for item in request.history:
            messages.append(HumanMessage(item.text) if item.role == "student" else AIMessage(item.text))
        messages.append(HumanMessage(request.message))

        state = await self.graph.ainvoke(
            {"messages": messages, "steps": 0, "final": None},
            config={"configurable": {"assistant_ctx": ctx, "catalog": self.catalog}, "recursion_limit": 4 * self.settings.max_steps + 4},
        )
        calls = {c["id"]: c for m in state["messages"] if isinstance(m, AIMessage) for c in (m.tool_calls or [])}
        steps = []
        for m in state["messages"]:
            if isinstance(m, ToolMessage):
                call = calls.get(m.tool_call_id, {})
                steps.append({"tool": m.name, "args": call.get("args", {}), "result": _parsed(m.content)})
        response = self._clean(state["final"] or {}, request)
        response.meta = Meta(prompt_version=PROMPT_VERSION, model_id=self.settings.llm_model,
                             latency_ms=int((time.perf_counter() - started) * 1000))
        return response, {"snapshot": messages[0].content.split("Student snapshot:\n", 1)[-1], "steps": steps}

    def _clean(self, final: dict, request: ReplyRequest) -> ReplyResponse:
        """Keeps the reply inside the contract's limits; drops links to anything the student cannot open."""
        reply = strip_markup(str(final.get("reply") or ""))
        if not reply:
            raise EmptyReply()
        if len(reply) > MAX_REPLY:
            reply = reply[: MAX_REPLY - 1].rstrip() + "…"

        suggestions = [strip_markup(str(s)) for s in (final.get("suggestions") or [])]
        suggestions = [s for s in suggestions if s]
        suggestions = [s for s in suggestions if len(s) <= MAX_SUGGESTION][:3]

        known = self.catalog.known_link_refs()
        if request.context.mentor and request.context.mentor.id:
            known.add(request.context.mentor.id)
        links: list[Link] = []
        for raw in final.get("links") or []:
            raw = raw if isinstance(raw, dict) else getattr(raw, "model_dump", lambda: {})()
            try:
                link = Link.model_validate(raw)
            except ValueError:
                continue
            if link.kind == "track":
                track = self.catalog.track(link.ref)
                link.ref = track["code"] if track else ""
            ok = (link.kind in PAGE_KINDS and not link.ref) or (link.kind not in PAGE_KINDS and link.ref in known)
            if ok and all(existing.kind != link.kind or existing.ref != link.ref for existing in links):
                links.append(link)
        links = links[:3]

        topic = final.get("topic") if final.get("topic") in TOPICS else "small_talk"
        return ReplyResponse(reply=reply, suggestions=suggestions, links=links, topic=topic,
                             meta=Meta(prompt_version=PROMPT_VERSION))
