"""Composition root: builds every dependency once, at startup."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.core.config import Settings
from app.core.security import Authenticator, build_authenticator
from app.providers.base import LlmProvider, SttProvider, TtsProvider
from app.providers.elevenlabs import ElevenLabsStt, ElevenLabsTts, FallbackStt, FallbackTts
from app.providers.fake import FakeLlm, FakeStt, FakeTts
from app.providers.groq.client import GroqHttpClient
from app.providers.groq.llm import GroqLlm
from app.providers.groq.speech import GroqStt, GroqTts
from app.services.prompts import PromptStore
from app.services.result_service import ResultService
from app.services.turn_service import TurnService


@dataclass
class Container:
    settings: Settings
    auth: Authenticator
    turn_service: TurnService
    result_service: ResultService
    _closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def aclose(self) -> None:
        for close in self._closers:
            await close()


def build_container(settings: Settings) -> Container:
    closers: list[Callable[[], Awaitable[None]]] = []
    llm: LlmProvider
    stt: SttProvider
    tts: TtsProvider
    if settings.fake_models:
        llm, stt, tts = FakeLlm(settings.interview_language), FakeStt(), FakeTts()
    else:
        client = GroqHttpClient(api_key=settings.groq_key_value, base_url=settings.groq_base_url)
        closers.append(client.aclose)
        llm, stt, tts = GroqLlm(client, settings), GroqStt(client, settings), GroqTts(client, settings)
        if settings.stt_provider == "elevenlabs":
            scribe = ElevenLabsStt(settings)
            closers.append(scribe.aclose)
            stt = FallbackStt(scribe, stt, "elevenlabs", "groq-whisper")
        if settings.tts_provider == "elevenlabs":
            voice = ElevenLabsTts(settings)
            closers.append(voice.aclose)
            tts = FallbackTts(voice, tts, "elevenlabs", "groq-orpheus")

    prompts = PromptStore(
        settings.prompts_dir,
        {
            "discovery_turn": settings.prompt_turn_version,
            "discovery_result": settings.prompt_result_version,
        },
    )
    return Container(
        settings=settings,
        auth=build_authenticator(settings),
        turn_service=TurnService(settings=settings, llm=llm, stt=stt, tts=tts, prompts=prompts),
        result_service=ResultService(settings=settings, llm=llm, prompts=prompts, tts=tts),
        _closers=closers,
    )
