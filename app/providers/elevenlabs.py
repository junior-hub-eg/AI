"""ElevenLabs Scribe speech-to-text (best measured accuracy on Egyptian Arabic + English code-switching).

Only metadata is logged (status, error codes, latency), never audio or transcripts.
"""

from __future__ import annotations

import io
import logging
import time
import wave

import httpx

from app.core.config import Settings
from app.core.logging import log_event
from app.providers.base import SpeechAudio, SttProvider, TtsProvider
from app.providers.errors import (
    ProviderAuthError,
    ProviderBadOutput,
    ProviderError,
    ProviderRateLimited,
    ProviderRejected,
    ProviderServerError,
    ProviderTimeout,
)

logger = logging.getLogger(__name__)

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"


class ElevenLabsStt:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._model = settings.elevenlabs_stt_model
        self._language = settings.stt_language
        self._keyterms = [t.strip() for t in settings.stt_keyterms.split(",") if t.strip()][:100]
        self._timeout = settings.stt_timeout_seconds
        self._client = client or httpx.AsyncClient(
            base_url=ELEVENLABS_BASE_URL,
            headers={"xi-api-key": settings.elevenlabs_key_value},
            timeout=httpx.Timeout(settings.stt_timeout_seconds, connect=5.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transcribe(self, audio: bytes, *, filename: str, mime_type: str) -> str:
        data: dict[str, str | list[str]] = {"model_id": self._model, "tag_audio_events": "false"}
        if self._language:
            data["language_code"] = self._language
        if self._keyterms:
            data["keyterms"] = self._keyterms
        started = time.perf_counter()
        try:
            response = await self._client.post(
                "/v1/speech-to-text",
                data=data,
                files={"file": (filename, audio, mime_type)},
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            log_event(logger, logging.WARNING, "elevenlabs_timeout", timeout_s=self._timeout)
            raise ProviderTimeout("elevenlabs speech-to-text timed out") from None
        except httpx.TransportError as exc:
            log_event(logger, logging.WARNING, "elevenlabs_network_error", error=type(exc).__name__)
            raise ProviderServerError(f"elevenlabs network error: {type(exc).__name__}") from None
        ms = round((time.perf_counter() - started) * 1000)
        if not response.is_success:
            self._raise_for_error(response, ms)
        try:
            text = str(response.json()["text"])
        except (ValueError, KeyError, TypeError):
            raise ProviderBadOutput("malformed ElevenLabs transcription response") from None
        log_event(logger, logging.INFO, "stt_done", provider="elevenlabs", model=self._model, ms=ms)
        return text

    @staticmethod
    def _raise_for_error(response: httpx.Response, ms: int) -> None:
        status = response.status_code
        code = ""
        try:
            detail = response.json().get("detail", {})
            code = str(detail.get("status", "")) if isinstance(detail, dict) else ""
        except (ValueError, AttributeError):
            pass
        log_event(logger, logging.WARNING, "elevenlabs_error", status=status, error_code=code, ms=ms)
        if status in (401, 403):
            raise ProviderAuthError("ElevenLabs rejected the API key (check ELEVENLABS_API_KEY in .env)")
        if status == 429:
            raise ProviderRateLimited("ElevenLabs rate limited / quota used up")
        if status >= 500:
            raise ProviderServerError(f"ElevenLabs returned {status}")
        raise ProviderRejected(f"ElevenLabs rejected the request ({status} {code})".strip())


class FallbackStt:
    """Try the primary speech-to-text provider; on any provider failure use the backup."""

    def __init__(
        self, primary: SttProvider, backup: SttProvider, primary_name: str, backup_name: str
    ) -> None:
        self._primary, self._backup = primary, backup
        self._names = (primary_name, backup_name)

    async def transcribe(self, audio: bytes, *, filename: str, mime_type: str) -> str:
        try:
            return await self._primary.transcribe(audio, filename=filename, mime_type=mime_type)
        except ProviderError as exc:
            log_event(
                logger,
                logging.WARNING,
                "stt_fallback",
                failed=self._names[0],
                reason=type(exc).__name__,
                using=self._names[1],
            )
            return await self._backup.transcribe(audio, filename=filename, mime_type=mime_type)


def pcm16_to_wav(pcm: bytes, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


class ElevenLabsTts:
    """ElevenLabs text-to-speech (natural Arabic voices). Returns WAV like the rest of the pipeline."""

    _RATE = 16000

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._voice = settings.elevenlabs_voice_id
        self._model = settings.elevenlabs_tts_model
        self._timeout = settings.tts_timeout_seconds
        self._client = client or httpx.AsyncClient(
            base_url=ELEVENLABS_BASE_URL,
            headers={"xi-api-key": settings.elevenlabs_key_value},
            timeout=httpx.Timeout(settings.tts_timeout_seconds, connect=5.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def speak(self, text: str) -> SpeechAudio:
        started = time.perf_counter()
        try:
            response = await self._client.post(
                f"/v1/text-to-speech/{self._voice}",
                params={"output_format": f"pcm_{self._RATE}"},
                json={
                    "text": text,
                    "model_id": self._model,
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0},
                },
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            log_event(logger, logging.WARNING, "elevenlabs_timeout", path="tts", timeout_s=self._timeout)
            raise ProviderTimeout("elevenlabs text-to-speech timed out") from None
        except httpx.TransportError as exc:
            log_event(
                logger, logging.WARNING, "elevenlabs_network_error", path="tts", error=type(exc).__name__
            )
            raise ProviderServerError(f"elevenlabs network error: {type(exc).__name__}") from None
        ms = round((time.perf_counter() - started) * 1000)
        if not response.is_success:
            ElevenLabsStt._raise_for_error(response, ms)
        if not response.content:
            raise ProviderBadOutput("ElevenLabs returned no audio")
        log_event(logger, logging.INFO, "tts_done", provider="elevenlabs", model=self._model, ms=ms)
        return SpeechAudio(pcm16_to_wav(response.content, self._RATE), "audio/wav")


class FallbackTts:
    def __init__(
        self, primary: TtsProvider, backup: TtsProvider, primary_name: str, backup_name: str
    ) -> None:
        self._primary, self._backup = primary, backup
        self._names = (primary_name, backup_name)

    async def speak(self, text: str) -> SpeechAudio:
        try:
            return await self._primary.speak(text)
        except ProviderError as exc:
            log_event(
                logger,
                logging.WARNING,
                "tts_fallback",
                failed=self._names[0],
                reason=type(exc).__name__,
                using=self._names[1],
            )
            return await self._backup.speak(text)
