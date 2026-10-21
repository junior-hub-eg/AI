"""The Cohere path end to end, with Cohere's client replaced by a script (no network, no key)."""

import asyncio
import json
import uuid

import pytest

pytest.importorskip("langchain_cohere")

from cohere import AssistantMessageResponse, ToolCallV2, ToolCallV2Function, V2ChatResponse  # noqa: E402
from langchain_cohere import ChatCohere  # noqa: E402

from assistant.assistant import Assistant  # noqa: E402
from assistant.config import Settings  # noqa: E402
from tests.assistant.conftest import make_request  # noqa: E402


def cohere_reply(tool: str, args: dict) -> V2ChatResponse:
    call = ToolCallV2(id=f"call_{uuid.uuid4().hex[:8]}", type="function",
                      function=ToolCallV2Function(name=tool, arguments=json.dumps(args, ensure_ascii=False)))
    return V2ChatResponse(id=uuid.uuid4().hex, finish_reason="TOOL_CALL",
                          message=AssistantMessageResponse(role="assistant", tool_calls=[call], tool_plan="..."))


def test_a_cohere_model_looks_up_data_then_responds(monkeypatch):
    monkeypatch.setenv("COHERE_API_KEY", "test")
    model = ChatCohere(model="command-a-03-2025")
    requests = []

    def chat(**kwargs):
        requests.append(kwargs)
        roles = [m["role"] if isinstance(m, dict) else getattr(m, "role", None) for m in kwargs["messages"]]
        if "tool" not in roles:
            return cohere_reply("get_my_learning", {})
        return cohere_reply("respond", {"reply": "الدرس الجاي Functions، كمّل من Try it.", "topic": "learning",
                                        "suggestions": ["اشرحلي الـ functions"],
                                        "links": [{"kind": "lesson", "ref": "dab266be-e6a4-5efd-a5f4-503784941482", "label": "Functions"}]})

    async def achat(**kwargs):
        return chat(**kwargs)

    object.__setattr__(model.client.v2, "chat", chat)
    object.__setattr__(model.async_client.v2, "chat", achat)  # the service runs the graph async
    settings = Settings(llm_model="cohere:command-a-03-2025", max_steps=3, auth_disabled=True)
    response, tools = asyncio.run(Assistant(model, settings).reply(make_request(message="الدرس الجاي إيه؟")))

    assert tools == ["get_my_learning"]
    assert response.reply.startswith("الدرس الجاي Functions")
    assert [(link.kind, link.label) for link in response.links] == [("lesson", "Functions")]
    assert all(r["tool_choice"] == "REQUIRED" for r in requests)
    assert all(r["citation_options"] == {"mode": "OFF"} for r in requests)  # no <co> tags in the text
    # The full schema reaches Cohere, so it knows the topics.
    respond_spec = next(t for t in requests[0]["tools"] if t.function.name == "respond")
    assert "wellbeing" in respond_spec.function.parameters["properties"]["topic"]["enum"]
    # The lookup result went back as a tool message with the lesson data.
    tool_messages = [m for m in requests[1]["messages"] if (m["role"] if isinstance(m, dict) else m.role) == "tool"]
    assert tool_messages and "Functions" in json.dumps(tool_messages[0], default=str, ensure_ascii=False)
