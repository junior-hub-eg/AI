from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Callable

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from assistant.schemas import AssistantContext, ReplyRequest

ROOT = Path(__file__).resolve().parents[2] / "assistant"
PERSONAS = ROOT / "mock" / "contexts"


def load_context(name: str) -> dict:
    return json.loads((PERSONAS / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def context() -> Callable[[str], AssistantContext]:
    return lambda name: AssistantContext.model_validate(load_context(name))


def make_request(persona: str = "frontend_beginner", message: str = "عندي كام XP؟", **extra: Any) -> ReplyRequest:
    return ReplyRequest(conversation_id=uuid.uuid4(), student_ref=uuid.uuid4(), message=message,
                        context=load_context(persona), **extra)


def tool_call(name: str, **args: Any) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}"}])


class ScriptedModel(BaseChatModel):
    """Answers with `script(messages, bound_tool_names)`."""

    script: Any
    bound: list[str] | None = None

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        names = [getattr(t, "name", None) or t.get("name") for t in tools]
        return ScriptedModel(script=self.script, bound=names)

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self.script(messages, self.bound or []))])
