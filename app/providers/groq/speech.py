"""Groq speech-to-text and text-to-speech providers."""

from __future__ import annotations

import asyncio
import logging
import time

from app.core.config import Settings
from app.core.logging import log_event
from app.providers.base import SpeechAudio
from app.providers.groq.client import GroqHttpClient
from app.services.text import chunk_text
from app.services.wav import join_wavs

logger = logging.getLogger(__name__)


class GroqStt:
    def __init__(self, client: GroqHttpClient, settings: Settings) -> None:
        self._client = client
        self._model = settings.stt_model
        self._language = settings.stt_language
        self._timeout = settings.stt_timeout_seconds
        self._prompt = settings.stt_prompt

    async def transcribe(self, audio: bytes, *, filename: str, mime_type: str) -> str:
        started = time.perf_counter()
        text = await self._client.transcribe(
            model=self._model,
            audio=audio,
            filename=filename,
            mime_type=mime_type,
            language=self._language,
            timeout=self._timeout,
            prompt=self._prompt,
        )
        ms = round((time.perf_counter() - started) * 1000)
        log_event(logger, logging.INFO, "stt_done", provider="groq", model=self._model, ms=ms)
        return text


class GroqTts:
    def __init__(self, client: GroqHttpClient, settings: Settings) -> None:
        self._client = client
        self._model = settings.tts_model
        self._voice = settings.tts_voice
        self._max_chars = settings.tts_max_chars
        self._timeout = settings.tts_timeout_seconds

    async def speak(self, text: str) -> SpeechAudio:
        # Chunks are synthesised in parallel: total time ~ the slowest chunk, not the sum.
        parts = await asyncio.gather(
            *(
                self._client.speak(model=self._model, voice=self._voice, text=chunk, timeout=self._timeout)
                for chunk in chunk_text(text, self._max_chars)
            )
        )
        return SpeechAudio(join_wavs(parts), "audio/wav")
