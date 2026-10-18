"""The Groq adapters, exercised against a fake HTTP transport (no network)."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import ProviderUnavailable
from app.main import create_app
from app.providers.base import LlmTask
from app.providers.errors import ProviderAuthError, ProviderExhausted, ProviderRateLimited
from app.providers.groq.client import GroqHttpClient
from app.providers.groq.llm import GroqLlm
from app.providers.groq.speech import GroqStt, GroqTts
from app.services.wav import silent_wav
from tests.conftest import TRACKS, make_settings, turn_body


def completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]})


def groq_client(handler) -> GroqHttpClient:
    return GroqHttpClient(
        api_key="gsk_test", base_url="https://api.groq.com/openai/v1", transport=httpx.MockTransport(handler)
    )


def settings() -> Settings:
    return make_settings(fake_models=False, groq_api_key="gsk_test")


def parse_q(data):
    if not data["question_text"].endswith("?"):
        raise ValueError("must end with a question mark")
    return data["question_text"]


async def run_llm(handler, parse=parse_q):
    llm = GroqLlm(groq_client(handler), settings())
    return await llm.generate_json(
        task=LlmTask.TURN, messages=[{"role": "user", "content": "hi JSON"}], parse=parse
    )


async def test_sends_expected_chat_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"] = str(request.url), request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return completion('{"question_text": "Fun?"}')

    result = await run_llm(handler)
    assert result.value == "Fun?" and result.model_id == "openai/gpt-oss-20b"
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["auth"] == "Bearer gsk_test"
    body = seen["body"]
    assert body["response_format"] == {"type": "json_object"}
    assert body["reasoning_effort"] == "low" and body["max_completion_tokens"] == 1024


async def test_json_wrapped_in_code_fence_is_accepted():
    result = await run_llm(lambda r: completion('```json\n{"question_text": "Fun?"}\n```'))
    assert result.value == "Fun?"


async def test_invalid_output_triggers_one_repair_on_same_model():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            return completion('{"question_text": "not a question"}')
        return completion('{"question_text": "Fixed?"}')

    result = await run_llm(handler)
    assert result.value == "Fixed?" and result.model_id == "openai/gpt-oss-20b"
    assert calls[1]["model"] == calls[0]["model"]
    assert "could not be used" in calls[1]["messages"][-1]["content"]
    assert "not a question" in calls[1]["messages"][-2]["content"]


async def test_rate_limit_switches_to_fallback_model():
    models = []

    def handler(request):
        model = json.loads(request.content)["model"]
        models.append(model)
        if model == "openai/gpt-oss-20b":
            return httpx.Response(
                429, headers={"retry-after": "3"}, json={"error": {"code": "rate_limit_exceeded"}}
            )
        return completion('{"question_text": "Hello?"}')

    result = await run_llm(handler)
    assert models == ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
    assert result.model_id == "openai/gpt-oss-120b"


async def test_server_error_and_timeout_fall_back():
    def handler(request):
        if json.loads(request.content)["model"] == "openai/gpt-oss-20b":
            raise httpx.ReadTimeout("slow")
        return completion('{"question_text": "Hello?"}')

    assert (await run_llm(handler)).model_id == "openai/gpt-oss-120b"


async def test_everything_failing_raises_exhausted():
    with pytest.raises(ProviderExhausted):
        await run_llm(lambda r: httpx.Response(503, json={}))


async def test_bad_key_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, json={"error": {"code": "invalid_api_key"}})

    with pytest.raises(ProviderAuthError):
        await run_llm(handler)
    assert len(calls) == 1


async def test_empty_completion_is_retried_then_falls_back():
    def handler(request):
        if json.loads(request.content)["model"] == "openai/gpt-oss-20b":
            return completion("")
        return completion('{"question_text": "Ok?"}')

    assert (await run_llm(handler)).model_id == "openai/gpt-oss-120b"


async def test_rate_limited_error_carries_retry_after():
    client = groq_client(lambda r: httpx.Response(429, headers={"retry-after": "7"}, json={}))
    with pytest.raises(ProviderRateLimited) as info:
        await client.chat_json(
            model="m", messages=[], temperature=0, max_completion_tokens=10, reasoning_effort="", timeout=5
        )
    assert info.value.retry_after == 7.0


async def test_transcription_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(200, json={"text": " I like robots "})

    stt = GroqStt(groq_client(handler), settings())
    text = await stt.transcribe(b"AUDIO", filename="answer.webm", mime_type="audio/webm")
    assert text == " I like robots "
    assert seen["url"].endswith("/audio/transcriptions")
    for needle in (b"whisper-large-v3", b'name="language"', b"\r\nar\r\n", b"answer.webm", b"AUDIO"):
        assert needle in seen["body"]


async def test_tts_splits_long_text_and_joins_audio():
    inputs = []

    def handler(request):
        body = json.loads(request.content)
        inputs.append(body["input"])
        assert body["response_format"] == "wav" and body["voice"] == "lulwa"
        return httpx.Response(200, content=silent_wav(0.1))

    tts = GroqTts(groq_client(handler), settings())
    speech = await tts.speak("This is the first sentence of the question. " * 8)
    assert len(inputs) >= 2 and all(len(i) <= 200 for i in inputs)
    assert speech.mime_type == "audio/wav" and speech.data.startswith(b"RIFF")


async def test_end_to_end_with_groq_adapters_and_tts_failure_is_non_fatal():
    """Whole /turns request through the real adapters; TTS fails, text still returned."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/chat/completions"):
            return completion('{"question_text": "Nice! What do you love about games?"}')
        if path.endswith("/audio/speech"):
            return httpx.Response(400, json={"error": {"code": "model_terms_required"}})
        raise AssertionError(path)

    from app.container import build_container

    container = build_container(settings())
    container.turn_service._llm = GroqLlm(groq_client(handler), settings())
    container.turn_service._tts = GroqTts(groq_client(handler), settings())

    from fastapi.testclient import TestClient

    with TestClient(create_app(settings(), container=container)) as c:
        answer = {"order_index": 1, "question_text": "Q?", "transcript": "I play games."}
        r = c.post("/v1/discovery/turns", json=turn_body(answer=answer, tracks=TRACKS))
    assert r.status_code == 200
    q = r.json()["next_question"]
    assert q["question_text"] == "Nice! What do you love about games?"
    assert q["audio_base64"] is None
    assert r.json()["meta"]["model_id"] == "openai/gpt-oss-20b"


async def test_all_models_down_gives_503_provider_unavailable():
    from fastapi.testclient import TestClient

    from app.container import build_container

    container = build_container(settings())
    container.turn_service._llm = GroqLlm(groq_client(lambda r: httpx.Response(500, json={})), settings())
    with TestClient(create_app(settings(), container=container)) as c:
        answer = {"order_index": 1, "question_text": "Q?", "transcript": "hi there"}
        r = c.post("/v1/discovery/turns", json=turn_body(answer=answer))
    assert r.status_code == 503 and r.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert ProviderUnavailable.status_code == 503
    assert base64 is not None
