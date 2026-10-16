"""One interview turn: answer (text or audio) in -> next spoken question out."""

from __future__ import annotations

import asyncio
import base64
import logging
import time

from app.core.config import Settings
from app.core.errors import AudioUnintelligible, DeadlineExceeded
from app.core.logging import log_event
from app.providers.base import LlmProvider, LlmTask, SttProvider, TtsProvider
from app.providers.errors import ProviderError
from app.schemas.common import QA, Meta
from app.schemas.turn import AnsweredOut, AnswerIn, QuestionOut, TurnRequest, TurnResponse
from app.services.audio import decode_audio
from app.services.errors_map import to_app_error
from app.services.prompt_builder import build_turn_messages
from app.services.prompts import PromptStore
from app.services.question_policy import validate_question
from app.services.text import clean_transcript, collapse_whitespace

logger = logging.getLogger(__name__)
FIXED_MODEL_ID = "fixed"


class TurnService:
    def __init__(
        self,
        *,
        settings: Settings,
        llm: LlmProvider,
        stt: SttProvider,
        tts: TtsProvider,
        prompts: PromptStore,
    ) -> None:
        self._s = settings
        self._llm, self._stt, self._tts = llm, stt, tts
        self._prompt = prompts.get("discovery_turn")
        # The opening question never changes and holds no student data, so its
        # audio is generated once. Saves a TTS call on every interview.
        self._opening_audio: tuple[str, str] | None = None

    async def run(self, req: TurnRequest) -> TurnResponse:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._s.turn_deadline_seconds):
                response = await self._run(req, started)
        except TimeoutError:
            raise DeadlineExceeded("The turn took too long") from None
        except ProviderError as exc:
            raise to_app_error(exc) from None
        return response

    async def _run(self, req: TurnRequest, started: float) -> TurnResponse:
        answered: AnsweredOut | None = None
        conversation = list(req.history)
        answered_count = conversation[-1].order_index if conversation else 0

        if req.answer is not None:
            transcript = await self._transcript_of(req.answer)
            answered = AnsweredOut(order_index=req.answer.order_index, transcript=transcript)
            conversation.append(
                QA(
                    order_index=req.answer.order_index,
                    question_text=req.answer.question_text,
                    transcript=transcript,
                )
            )
            answered_count = req.answer.order_index

        if answered_count >= req.max_questions:
            return self._response(req, answered, None, FIXED_MODEL_ID, started)

        number = answered_count + 1
        if number == 1:
            text, model_id = self._s.opening_question, FIXED_MODEL_ID
        else:
            text, model_id = await self._next_question(req, conversation, number)

        audio_b64 = mime = None
        if req.speak:
            audio = await self._speak(text, cacheable=number == 1)
            if audio:
                audio_b64, mime = audio
        question = QuestionOut(
            order_index=number, question_text=text, audio_base64=audio_b64, audio_mime_type=mime
        )
        return self._response(req, answered, question, model_id, started)

    # ---------------------------------------------------------------- steps
    async def _transcript_of(self, answer: AnswerIn) -> str:
        if answer.transcript:
            return collapse_whitespace(answer.transcript)
        audio = decode_audio(
            answer.audio_base64 or "",
            answer.audio_mime_type or "",
            max_bytes=self._s.max_audio_bytes,
            max_seconds=self._s.max_audio_seconds,
        )
        text = clean_transcript(
            await self._stt.transcribe(audio.data, filename=audio.filename, mime_type=audio.mime_type)
        )
        if not text:
            raise AudioUnintelligible("No speech could be understood in the recording")
        return text[: self._s.max_text_chars]

    async def _next_question(self, req: TurnRequest, conversation: list[QA], number: int) -> tuple[str, str]:
        messages = build_turn_messages(
            self._prompt,
            self._s,
            tracks=req.tracks,
            grade=req.grade,
            conversation=conversation,
            question_number=number,
            max_questions=req.max_questions,
        )
        result = await self._llm.generate_json(
            task=LlmTask.TURN,
            messages=messages,
            parse=lambda data: validate_question(str(data["question_text"])),
        )
        return result.value, result.model_id

    async def _speak(self, text: str, *, cacheable: bool) -> tuple[str, str] | None:
        if cacheable and self._opening_audio:
            return self._opening_audio
        try:
            speech = await asyncio.wait_for(self._tts.speak(text), timeout=self._s.tts_timeout_seconds)
        except (ProviderError, TimeoutError) as exc:
            # Speech is optional: the text question is always returned.
            log_event(logger, logging.WARNING, "tts_failed", reason=type(exc).__name__)
            return None
        encoded = (base64.b64encode(speech.data).decode("ascii"), speech.mime_type)
        if cacheable:
            self._opening_audio = encoded
        return encoded

    def _response(
        self,
        req: TurnRequest,
        answered: AnsweredOut | None,
        question: QuestionOut | None,
        model_id: str,
        started: float,
    ) -> TurnResponse:
        return TurnResponse(
            interview_id=req.interview_id,
            answered=answered,
            next_question=question,
            finished=question is None,
            meta=Meta(
                prompt_version=self._prompt.label,
                model_id=model_id,
                latency_ms=round((time.perf_counter() - started) * 1000),
            ),
        )
