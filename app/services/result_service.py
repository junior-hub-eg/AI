"""Final step: whole interview in -> top 3 tracks with match % and reasons out."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import Settings
from app.core.errors import DeadlineExceeded, InvalidRequest
from app.core.logging import log_event
from app.providers.base import LlmProvider, LlmTask, TtsProvider
from app.providers.errors import ProviderError
from app.schemas.common import Meta
from app.schemas.result import RecommendationOut, ResultRequest, ResultResponse
from app.services.errors_map import to_app_error
from app.services.prompt_builder import build_result_messages
from app.services.prompts import PromptStore
from app.services.text import clean_spoken_text, split_sentences, truncate_words

REASON_MAX_CHARS = 300
SUMMARY_MAX_SENTENCES = 4
SUMMARY_MAX_CHARS = 700


class _LlmRecommendation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    track_code: str
    match_percent: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1)

    @field_validator("match_percent", mode="before")
    @classmethod
    def _numeric(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = re.sub(r"[^\d.]", "", value)
        if isinstance(value, float | str):
            value = round(float(value))
        return value


class _LlmResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    recommendations: list[_LlmRecommendation]
    summary: str = Field(min_length=1)
    # Same summary in Arabic script only, for TTS. Optional.
    summary_speech: str | None = None


logger = logging.getLogger(__name__)


def parse_result(data: dict[str, Any], allowed_codes: set[str]) -> tuple[list[RecommendationOut], str, str]:
    """Validate and normalise the model output. Raises ValueError when unusable."""
    parsed = _LlmResult.model_validate(data)
    seen: set[str] = set()
    valid: list[_LlmRecommendation] = []
    for rec in parsed.recommendations:
        code = rec.track_code.strip().upper()
        if code not in allowed_codes:
            raise ValueError("track_code must be one of the allowed track codes")
        if code in seen:
            raise ValueError("each track may appear only once")
        seen.add(code)
        valid.append(rec.model_copy(update={"track_code": code}))
    if len(valid) < 3:
        raise ValueError("recommendations must contain exactly 3 different tracks")
    top = sorted(valid, key=lambda r: r.match_percent, reverse=True)[:3]
    recommendations = [
        RecommendationOut(
            rank=rank,
            track_code=rec.track_code,
            match_percent=rec.match_percent,
            reason=truncate_words(clean_spoken_text(rec.reason), REASON_MAX_CHARS),
        )
        for rank, rec in enumerate(top, start=1)
    ]
    sentences = split_sentences(clean_spoken_text(parsed.summary))
    summary = truncate_words(" ".join(sentences[:SUMMARY_MAX_SENTENCES]), SUMMARY_MAX_CHARS)
    speech = clean_spoken_text(parsed.summary_speech or "") or summary
    speech = truncate_words(" ".join(split_sentences(speech)[: SUMMARY_MAX_SENTENCES + 1]), SUMMARY_MAX_CHARS)
    return recommendations, summary, speech


class ResultService:
    def __init__(
        self, *, settings: Settings, llm: LlmProvider, prompts: PromptStore, tts: TtsProvider | None = None
    ) -> None:
        self._s = settings
        self._llm = llm
        self._tts = tts
        self._prompt = prompts.get("discovery_result")

    async def run(self, req: ResultRequest) -> ResultResponse:
        count = len(req.responses)
        if not self._s.result_min_responses <= count <= self._s.result_max_responses:
            raise InvalidRequest(
                f"responses must contain {self._s.result_min_responses} to "
                f"{self._s.result_max_responses} items"
            )
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._s.result_deadline_seconds):
                return await self._run(req, started)
        except TimeoutError:
            raise DeadlineExceeded("The result took too long") from None
        except ProviderError as exc:
            raise to_app_error(exc) from None

    async def _run(self, req: ResultRequest, started: float) -> ResultResponse:
        codes = {t.code for t in req.tracks}
        messages = build_result_messages(
            self._prompt, self._s, tracks=req.tracks, grade=req.grade, responses=req.responses
        )
        result = await self._llm.generate_json(
            task=LlmTask.RESULT,
            messages=messages,
            parse=lambda data: parse_result(data, codes),
            context={"track_codes": [t.code for t in req.tracks]},
        )
        recommendations, summary, speech = result.value
        audio_b64 = mime = None
        if req.speak and self._tts:
            try:
                audio = await asyncio.wait_for(
                    self._tts.speak(speech), timeout=self._s.tts_timeout_seconds * 2
                )
                audio_b64, mime = base64.b64encode(audio.data).decode("ascii"), audio.mime_type
            except (ProviderError, TimeoutError) as exc:
                # Speech is optional: the text result is always returned.
                log_event(logger, logging.WARNING, "result_tts_failed", reason=type(exc).__name__)
        return ResultResponse(
            interview_id=req.interview_id,
            recommendations=recommendations,
            summary=summary,
            summary_audio_base64=audio_b64,
            summary_audio_mime_type=mime,
            meta=Meta(
                prompt_version=self._prompt.label,
                model_id=result.model_id,
                latency_ms=round((time.perf_counter() - started) * 1000),
            ),
        )
