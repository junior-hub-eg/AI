import httpx
import pytest

from app.providers.elevenlabs import ElevenLabsStt, FallbackStt
from app.providers.errors import ProviderAuthError, ProviderServerError
from tests.conftest import make_settings


def scribe(handler):
    settings = make_settings(
        stt_provider="elevenlabs", elevenlabs_api_key="xi-test", stt_keyterms="Minecraft, Python"
    )
    client = httpx.AsyncClient(base_url="https://api.elevenlabs.io", transport=httpx.MockTransport(handler))
    return ElevenLabsStt(settings, client=client)


async def test_scribe_request_shape_and_text():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(request.url), request.content
        return httpx.Response(200, json={"text": "بحب ألعب Minecraft", "language_code": "ara"})

    text = await scribe(handler).transcribe(b"AUDIO", filename="answer.webm", mime_type="audio/webm")
    assert text == "بحب ألعب Minecraft"
    assert seen["url"].endswith("/v1/speech-to-text")
    for needle in (b"scribe_v2", b'name="language_code"', b"\r\nar\r\n", b"Minecraft", b"Python", b"AUDIO"):
        assert needle in seen["body"]


async def test_scribe_bad_key_is_auth_error():
    with pytest.raises(ProviderAuthError):
        await scribe(
            lambda r: httpx.Response(401, json={"detail": {"status": "invalid_api_key"}})
        ).transcribe(b"A", filename="a.webm", mime_type="audio/webm")


class _Fails:
    async def transcribe(self, audio, *, filename, mime_type):
        raise ProviderServerError("down")


class _Works:
    async def transcribe(self, audio, *, filename, mime_type):
        return "from backup"


async def test_fallback_uses_whisper_when_scribe_fails():
    stt = FallbackStt(_Fails(), _Works(), "elevenlabs", "groq")
    assert await stt.transcribe(b"A", filename="a.webm", mime_type="audio/webm") == "from backup"


def test_elevenlabs_needs_a_key():
    with pytest.raises(ValueError):
        make_settings(fake_models=False, groq_api_key="gsk_x", stt_provider="elevenlabs")


async def test_elevenlabs_tts_returns_wav():
    from app.providers.elevenlabs import ElevenLabsTts

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, content=b"\x00\x01" * 1600)

    settings = make_settings(tts_provider="elevenlabs", elevenlabs_api_key="xi", elevenlabs_voice_id="VOICE1")
    client = httpx.AsyncClient(base_url="https://api.elevenlabs.io", transport=httpx.MockTransport(handler))
    audio = await ElevenLabsTts(settings, client=client).speak("أهلا")
    assert audio.data.startswith(b"RIFF") and audio.mime_type == "audio/wav"
    assert "/v1/text-to-speech/VOICE1" in seen["url"] and "pcm_16000" in seen["url"]


def test_elevenlabs_tts_needs_voice_id():
    with pytest.raises(ValueError):
        make_settings(
            fake_models=False, groq_api_key="gsk_x", tts_provider="elevenlabs", elevenlabs_api_key="xi"
        )
