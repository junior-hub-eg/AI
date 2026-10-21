"""A keyword-based stand-in for the LLM, for tests and for checking the wiring without an API key.

It follows the same loop as a real model: call one data tool, read its result, then call `respond`.
Its replies are plain summaries, not real answers.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

# (keywords, tool, args) — first match wins.
ROUTES: list[tuple[tuple[str, ...], str, dict]] = [
    (("xp", "نقط", "نقاط", "badge", "بادج", "شار", "streak", "ستريك"), "get_my_achievements", {}),
    (("درس", "lesson", "الجاي", "next", "وقفت"), "get_my_learning", {}),
    (("فريق", "squad", "سبرنت", "sprint", "تاسك", "task"), "get_my_squad", {}),
    (("منتور", "mentor"), "find_mentors", {}),
    (("وظيف", "job", "انترفيو", "interview", "شهاد", "certificate"), "find_practice_jobs", {}),
    (("اترشح", "ترشيح", "discovery", "نتيجة"), "get_discovery_result", {}),
    (("function", "فانكشن", "variable", "متغير"), "get_lesson_help", {"lesson": "Functions"}),
]


class FakeChatModel(BaseChatModel):
    model_name: str = "fake"

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools: Any, **kwargs: Any):  # noqa: D401 - same signature as real models
        return self

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        last = messages[-1]
        if isinstance(last, HumanMessage):
            text = str(last.content).lower()
            for keywords, tool_name, args in ROUTES:
                if any(k in text for k in keywords):
                    return _result(_call(tool_name, args))
            return _result(_respond("(تجربة) أنا مساعد Junior Hub. اسألني عن دروسك أو الـ XP أو فريقك.", "small_talk"))

        if isinstance(last, ToolMessage):
            try:
                data = json.loads(last.content)
                keys = ", ".join(list(data)[:6]) if isinstance(data, dict) else str(data)[:120]
            except (json.JSONDecodeError, TypeError):
                keys = str(last.content)[:120]
            return _result(_respond(f"(تجربة) جبت البيانات من {last.name}: {keys}", "my_progress"))

        return _result(_respond("(تجربة) تمام.", "small_talk"))


def _call(name: str, args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}"}])


def _respond(reply: str, topic: str) -> AIMessage:
    return _call("respond", {"reply": reply, "topic": topic, "suggestions": ["الدرس الجاي إيه؟"], "links": []})


def _result(message: AIMessage) -> ChatResult:
    return ChatResult(generations=[ChatGeneration(message=message)])
