import asyncio

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from assistant.assistant import Assistant, EmptyReply
from assistant.config import Settings
from assistant.fake_llm import FakeChatModel
from assistant.tools import RESPOND
from tests.assistant.conftest import ScriptedModel, make_request, tool_call

SETTINGS = Settings(llm_model="scripted", max_steps=3, auth_disabled=True)


def reply(model, request=None):
    return asyncio.run(Assistant(model, SETTINGS).reply(request or make_request()))


def test_a_lookup_then_respond():
    def script(messages, bound):
        if not isinstance(messages[-1], ToolMessage):
            return tool_call("get_my_achievements")
        assert '"total_xp": 100' in messages[-1].content
        return tool_call(RESPOND, reply="معاك 100 XP 👏", topic="my_progress", suggestions=["أزود XP إزاي؟"],
                         links=[{"kind": "achievements"}])

    response, tools = reply(ScriptedModel(script=script))
    assert response.reply == "معاك 100 XP 👏"
    assert tools == ["get_my_achievements"]
    assert [link.kind for link in response.links] == ["achievements"]
    assert response.meta.prompt_version == "assistant@v1"


def test_the_snapshot_answers_simple_questions_without_tools():
    def script(messages, bound):
        assert "100 XP" in messages[0].content and "Next lesson: Functions" in messages[0].content
        return tool_call(RESPOND, reply="100 XP", topic="my_progress")

    response, tools = reply(ScriptedModel(script=script))
    assert tools == [] and response.reply == "100 XP"


def test_after_max_steps_only_respond_is_offered():
    offered = []

    def script(messages, bound):
        offered.append(bound)
        # A model that would keep looking things up forever.
        return tool_call(RESPOND, reply="خلاص", topic="learning") if bound == [RESPOND] else tool_call("get_my_learning")

    response, tools = reply(ScriptedModel(script=script))
    assert response.reply == "خلاص"
    assert len(tools) == SETTINGS.max_steps
    assert offered[-1] == [RESPOND] and len(offered[0]) > 1


def test_links_and_suggestions_are_kept_within_the_contract():
    functions_id = "dab266be-e6a4-5efd-a5f4-503784941482"
    script = lambda messages, bound: tool_call(
        RESPOND, reply="x" * 2500, topic="not-a-topic",
        suggestions=["ok", "y" * 90, "", "two", "three", "four"],
        links=[{"kind": "lesson", "ref": functions_id}, {"kind": "lesson", "ref": "made-up"},
               {"kind": "track", "ref": "ui/ux"}, {"kind": "squad", "ref": "x"}, {"kind": "jobs"}, {"kind": "mentor", "ref": "?"}])
    response, _ = reply(ScriptedModel(script=script))
    assert len(response.reply) == 2000 and response.reply.endswith("…")
    assert response.topic == "small_talk"
    assert response.suggestions == ["ok", "two", "three"]
    assert [(link.kind, link.ref) for link in response.links] == [("lesson", functions_id), ("track", "UIUX"), ("jobs", "")]


def test_a_plain_text_answer_is_accepted():
    response, _ = reply(ScriptedModel(script=lambda messages, bound: AIMessage(content=[{"type": "text", "text": "أهلاً!"}])))
    assert response.reply == "أهلاً!"


def test_an_empty_answer_is_an_error():
    with pytest.raises(EmptyReply):
        reply(ScriptedModel(script=lambda messages, bound: tool_call(RESPOND, reply="  ", topic="small_talk")))


def test_history_is_sent_in_order():
    seen = {}

    def script(messages, bound):
        seen["roles"] = [type(m).__name__ for m in messages]
        return tool_call(RESPOND, reply="تمام", topic="small_talk")

    reply(ScriptedModel(script=script), make_request(history=[{"role": "student", "text": "hi"}, {"role": "assistant", "text": "hello"}]))
    assert seen["roles"] == ["SystemMessage", "HumanMessage", "AIMessage", "HumanMessage"]


def test_the_fake_model_runs_end_to_end():
    response, tools = reply(FakeChatModel(), make_request(message="الدرس الجاي إيه؟"))
    assert tools == ["get_my_learning"] and response.reply.startswith("(تجربة)")


def test_citation_tags_are_removed_from_the_reply():
    tagged = "خلصت <co>المتغيرات</co: 0:[0]> وفاضلك <co: 1>تلات دروس</co: 1>."
    response, _ = reply(ScriptedModel(script=lambda messages, bound: tool_call(
        RESPOND, reply=tagged, topic="learning", suggestions=["<co>الدرس الجاي</co: 0:[0]>؟"])))
    assert response.reply == "خلصت المتغيرات وفاضلك تلات دروس."
    assert response.suggestions == ["الدرس الجاي؟"]
