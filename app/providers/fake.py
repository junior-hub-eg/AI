"""Offline providers: no network, deterministic. For tests and UI work (FAKE_MODELS=true)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.providers.base import LlmResult, LlmTask, Message, SpeechAudio, T
from app.services.wav import silent_wav

_QUESTIONS = (
    "Nice! Which school subjects do you enjoy the most, and why?",
    "Do you like making things look good, or figuring out how they work?",
    "Can you tell me about a time something was hard and what you did?",
    "What games or apps do you love, and what makes them fun?",
    "Do you prefer working in a team or on your own?",
    "What have you been curious about lately?",
    "If you could build anything with technology, what would it be?",
)


class FakeLlm:
    model_id = "fake-llm"

    async def generate_json(
        self,
        *,
        task: LlmTask,
        messages: list[Message],
        parse: Callable[[dict[str, Any]], T],
        context: Mapping[str, Any] | None = None,
    ) -> LlmResult[T]:
        if task is LlmTask.TURN:
            answers = messages[-1]["content"].count("<student_answer>")
            data: dict[str, Any] = {"question_text": _QUESTIONS[answers % len(_QUESTIONS)]}
        else:
            codes = list((context or {}).get("track_codes", []))[:3]
            data = {
                "recommendations": [
                    {
                        "track_code": code,
                        "match_percent": pct,
                        "reason": f"You showed real interest that fits {code.title()}.",
                    }
                    for code, pct in zip(codes, (86, 74, 61), strict=False)
                ],
                "summary": (
                    "You love creating and solving problems. "
                    "These tracks fit what you told us. Have fun exploring them!"
                ),
            }
        return LlmResult(parse(data), self.model_id)


class FakeStt:
    """Audio starting with b'TEXT:' is returned as that text; anything else is canned."""

    async def transcribe(self, audio: bytes, *, filename: str, mime_type: str) -> str:
        if audio.startswith(b"TEXT:"):
            return audio[5:].decode("utf-8", errors="ignore")
        return "I like building small games and fixing computers."


class FakeTts:
    async def speak(self, text: str) -> SpeechAudio:
        return SpeechAudio(silent_wav(), "audio/wav")
