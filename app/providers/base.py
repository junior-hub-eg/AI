"""Provider contracts. Services depend on these, never on a concrete vendor."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, TypeVar

T = TypeVar("T")
Message = dict[str, str]


class LlmTask(StrEnum):
    TURN = "turn"
    RESULT = "result"


@dataclass(frozen=True)
class LlmResult[T]:
    value: T
    model_id: str


@dataclass(frozen=True)
class SpeechAudio:
    data: bytes
    mime_type: str


class LlmProvider(Protocol):
    async def generate_json(
        self,
        *,
        task: LlmTask,
        messages: list[Message],
        parse: Callable[[dict[str, Any]], T],
        context: Mapping[str, Any] | None = None,
    ) -> LlmResult[T]:
        """Return `parse(<json object produced by the model>)`.

        `parse` must raise ValueError/KeyError/TypeError for unusable output so
        the provider can ask the model to repair it or try another model.
        `context` is non-sensitive metadata used only by the fake provider.
        """


class SttProvider(Protocol):
    async def transcribe(self, audio: bytes, *, filename: str, mime_type: str) -> str:
        """Speech to text. Returns plain text (possibly empty)."""


class TtsProvider(Protocol):
    async def speak(self, text: str) -> SpeechAudio:
        """Text to speech. Returns WAV audio."""
