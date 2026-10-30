import base64
import json
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.main import create_app
from teaching.config import Settings
from teaching.schemas import (
    ConceptQuickCheckRequest,
    LessonRequest,
    LinkIdeasRequest,
    QuickCheckRequest,
    VideoLinksRequest,
    VideoSummaryRequest,
)
from teaching.service import BadAnswer, LlmTeachingAi, extract_json
from tests.conftest import make_settings

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
PUBLIC = KEY.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def token(audience="teaching-ai"):
    now = int(time.time())
    return jwt.encode({"aud": audience, "iss": "JuniorHub.Api", "iat": now, "nbf": now, "exp": now + 300, "jti": uuid.uuid4().hex},
                      PRIVATE, algorithm="RS256")


@pytest.fixture
def client():
    settings = Settings(_env_file=None, llm_model="fake", auth_public_key_pem=PUBLIC)
    with TestClient(create_app(make_settings(), teaching_settings=settings)) as c:
        c.headers["Authorization"] = f"Bearer {token()}"
        yield c


def test_a_call_without_the_teaching_token_is_rejected(client):
    body = {"track_name": "AI", "video_title": "Computer Vision", "subject": "Physics"}
    assert client.post("/v1/teaching/video-links", json=body, headers={"Authorization": ""}).status_code == 401
    assert client.post("/v1/teaching/video-links", json=body,
                       headers={"Authorization": f"Bearer {token('assistant-ai')}"}).status_code == 401


def test_video_links_give_a_three_point_summary_and_three_ideas(client):
    res = client.post("/v1/teaching/video-links", json={"track_name": "AI", "video_title": "Computer Vision", "subject": "Physics"})
    assert res.status_code == 200
    data = res.json()
    assert len(data["summary"]) == 3 and len(data["ideas"]) == 3
    assert data["meta"]["model_id"] == "fake"


def test_quick_check_has_the_count_asked_for(client):
    data = client.post("/v1/teaching/quick-check", json={"title": "Computer Vision", "count": 5}).json()
    assert len(data["questions"]) == 5
    assert all(0 <= q["answer_index"] < len(q["options"]) for q in data["questions"])


TRANSCRIPT = "Computer vision lets computers see. A camera turns the picture into numbers, and a model finds shapes."
SUMMARY = ["إيه هو", "بيشتغل إزاي", "بنستخدمه فين"]


def test_concept_video_summary_ideas_and_quick_check(client):
    summary = client.post("/v1/teaching/video-summary", json={"video_title": "Computer Vision", "transcript": TRANSCRIPT}).json()
    assert summary["what_it_is"] and summary["how_it_works"] and summary["where_used"]

    body = {"video_title": "Computer Vision", "summary": SUMMARY, "subject": "Physics", "grade": 9}
    first = client.post("/v1/teaching/link-ideas", json=body).json()["ideas"]
    again = client.post("/v1/teaching/link-ideas", json={**body, "avoid": first}).json()["ideas"]
    assert len(first) == len(again) == 3 and not set(first) & set(again)

    quiz = client.post("/v1/teaching/concept-quick-check", json={
        "video_title": "Computer Vision", "summary": SUMMARY, "subject": "Physics", "grade": 9,
        "link": "الكاميرا بتلتقط الضوء بالعدسات والانعكاس، وده نفس اللي بتدرسه في البصريات."}).json()
    assert len(quiz["questions"]) == 2
    assert all(0 <= q["answer_index"] < len(q["options"]) for q in quiz["questions"])


def test_concept_requests_are_checked(client):
    assert client.post("/v1/teaching/video-summary", json={"video_title": "CV", "transcript": "short"}).status_code == 400
    assert client.post("/v1/teaching/link-ideas", json={"video_title": "CV", "summary": [], "subject": "Physics"}).status_code == 400
    assert client.post("/v1/teaching/concept-quick-check", json={
        "video_title": "CV", "summary": SUMMARY, "subject": "Physics", "link": "x", "count": 9}).status_code == 400


def test_grammar_ocr_parse_lesson_and_feedback(client):
    image = base64.b64encode(b"\x89PNG fake image bytes").decode()
    text = client.post("/v1/teaching/grammar/ocr", json={"image_base64": image, "mime_type": "image/png"}).json()["text"]
    parsed = client.post("/v1/teaching/grammar/parse", json={"text": text}).json()
    assert parsed["sentences"][0]["words"][1]["role"] == "اسم إنّ"

    lesson = client.post("/v1/teaching/grammar/lesson", json={"topic_title": "إنّ وأخواتها"}).json()
    assert 3 <= len(lesson["points"]) <= 4 and len(lesson["examples"]) == 2 and lesson["practice"]["words"]

    feedback = client.post("/v1/teaching/grammar/feedback", json={
        "topic_title": "إنّ وأخواتها", "sentence": "إنّ محمدًا مجتهدٌ",
        "mistakes": [{"word": "محمدًا", "expected": "اسم إنّ", "given": "فاعل"}]}).json()
    assert feedback["items"][0]["guiding_questions"]
    assert feedback["similar_sentence"]["words"]


def test_grammar_ask_answers_the_question(client):
    data = client.post("/v1/teaching/grammar/ask", json={
        "topic_title": "كان وأخواتها", "question": "ليه الكلمة دي اسم كان؟", "context": "كان الطالبُ مجتهدًا",
        "history": [{"role": "student", "text": "يعني إيه ناسخ؟"}, {"role": "coach", "text": "بيغيّر إعراب الجملة."}]}).json()
    assert data["answer"]
    assert client.post("/v1/teaching/grammar/ask", json={"topic_title": "x", "question": ""}).status_code == 400


def test_invalid_requests_are_400(client):
    assert client.post("/v1/teaching/quick-check", json={"title": "x", "count": 50}).status_code == 400
    assert client.post("/v1/teaching/grammar/ocr", json={"image_base64": "abc", "mime_type": "image/gif"}).status_code == 400


# ----- the model-backed service, with a scripted model ----------------------------------------------------------

class Scripted(BaseChatModel):
    replies: list

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.replies.pop(0)))])


def ai(*replies: str) -> LlmTeachingAi:
    return LlmTeachingAi(Settings(_env_file=None), Scripted(replies=list(replies)))


def test_extract_json_reads_fenced_or_wrapped_objects():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Here: {"a": [1, 2]} done') == {"a": [1, 2]}


async def test_a_wrong_answer_is_asked_again_once():
    good = json.dumps({"summary": ["a", "b", "c"], "ideas": [{"title": "t", "text": "x"}] * 3}, ensure_ascii=False)
    result = await ai("not json", good).video_links(VideoLinksRequest(track_name="AI", video_title="CV", subject="Physics"))
    assert result.summary == ["a", "b", "c"]
    with pytest.raises(BadAnswer):
        await ai("{}", "{}").video_links(VideoLinksRequest(track_name="AI", video_title="CV", subject="Physics"))


async def test_quick_check_drops_questions_with_a_bad_answer_index():
    reply = json.dumps({"questions": [
        {"question": "q1", "options": ["a", "b"], "answer_index": 1},
        {"question": "q2", "options": ["a", "b"], "answer_index": 3},
    ]})
    result = await ai(reply).quick_check(QuickCheckRequest(title="t", count=2))
    assert [q.question for q in result.questions] == ["q1"]


async def test_lesson_uses_the_schema():
    word = {"word": "إنّ", "role": "حرف", "case": "مبني", "sign": "الفتح", "color": "gray"}
    sentence = {"text": "إنّ", "words": [word]}
    reply = json.dumps({"points": [{"title": "a", "text": "b"}] * 3, "examples": [sentence, sentence], "practice": sentence},
                       ensure_ascii=False)
    result = await ai(reply).lesson(LessonRequest(topic_title="إنّ وأخواتها"))
    assert result.practice.words[0].role == "حرف"


async def test_video_summary_and_link_ideas_use_the_schema():
    reply = json.dumps({"what_it_is": "a", "how_it_works": "b", "where_used": "c"})
    summary = await ai(reply).video_summary(VideoSummaryRequest(video_title="CV", transcript=TRANSCRIPT))
    assert (summary.what_it_is, summary.how_it_works, summary.where_used) == ("a", "b", "c")

    two_ideas = json.dumps({"ideas": ["x", "y"]})
    three = json.dumps({"ideas": ["x", "y", "z"]})
    result = await ai(two_ideas, three).link_ideas(LinkIdeasRequest(video_title="CV", summary=SUMMARY, subject="Math", avoid=["old"]))
    assert result.ideas == ["x", "y", "z"]


async def test_concept_quick_check_keeps_the_right_answer_when_it_mixes_the_options():
    reply = json.dumps({"questions": [
        {"question": "q1", "options": ["العدسة", "الشاشة", "البطارية", "الميكروفون"], "answer_index": 0},
        {"question": "q2", "options": ["a", "b"], "answer_index": 3},
        {"question": "q3", "options": ["a", "b", "c"], "answer_index": 2},
    ]}, ensure_ascii=False)
    result = await ai(reply).concept_quick_check(ConceptQuickCheckRequest(
        video_title="CV", summary=SUMMARY, subject="Physics", link="الكاميرا والعدسات"))
    assert [q.question for q in result.questions] == ["q1", "q3"]
    assert result.questions[0].options[result.questions[0].answer_index] == "العدسة"
    assert result.questions[1].options[result.questions[1].answer_index] == "c"
