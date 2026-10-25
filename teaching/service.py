"""The teaching AI: one structured call per request, with a JSON schema in the prompt and a check of the answer."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Protocol, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from . import prompts
from .config import Settings
from .schemas import (
    FeedbackRequest,
    FeedbackResponse,
    LessonRequest,
    LessonResponse,
    Meta,
    OcrRequest,
    OcrResponse,
    ParseRequest,
    ParseResponse,
    QuickCheckRequest,
    QuickCheckResponse,
    VideoLinksRequest,
    VideoLinksResponse,
)

logger = logging.getLogger("teaching")
T = TypeVar("T", bound=BaseModel)


class BadAnswer(Exception):
    """The model answered something that is not the JSON asked for, twice."""


class TeachingAi(Protocol):
    async def video_links(self, body: VideoLinksRequest) -> VideoLinksResponse: ...
    async def quick_check(self, body: QuickCheckRequest) -> QuickCheckResponse: ...
    async def ocr(self, body: OcrRequest) -> OcrResponse: ...
    async def parse(self, body: ParseRequest) -> ParseResponse: ...
    async def lesson(self, body: LessonRequest) -> LessonResponse: ...
    async def feedback(self, body: FeedbackRequest) -> FeedbackResponse: ...


def create_model(model_id: str, settings: Settings) -> BaseChatModel:
    from langchain.chat_models import init_chat_model

    extra: dict[str, Any] = {}
    if "gpt-oss" in model_id and settings.llm_reasoning_effort:
        extra["reasoning_effort"] = settings.llm_reasoning_effort
    return init_chat_model(model_id, temperature=settings.llm_temperature, max_retries=0, **extra)


def extract_json(text: str) -> Any:
    """The JSON object in the model's text, without ```json fences or words around it."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object")
    return json.loads(text[start : end + 1])


class LlmTeachingAi:
    def __init__(self, settings: Settings, model: BaseChatModel, fallback: BaseChatModel | None = None,
                 vision: BaseChatModel | None = None) -> None:
        self.settings, self.model, self.fallback, self.vision = settings, model, fallback, vision

    # ----- one structured call --------------------------------------------------------------------------------
    async def _call(self, model: BaseChatModel, messages: list) -> str:
        try:
            response = await model.ainvoke(messages)
        except Exception as exc:
            if self.fallback is not None and model is self.model and getattr(exc, "status_code", None) == 429:
                logger.warning("teaching model rate limited, using the fallback model")
                response = await self.fallback.ainvoke(messages)
            else:
                raise
        return str(response.content)

    async def _structured(self, system: str, payload: dict, shape: type[T]) -> T:
        schema = json.dumps(shape.model_json_schema(), ensure_ascii=False)
        messages: list = [
            SystemMessage(system + "\n\n" + prompts.JSON_RULE.format(schema=schema)),
            HumanMessage(json.dumps(payload, ensure_ascii=False)),
        ]
        for attempt in (1, 2):
            text = await self._call(self.model, messages)
            try:
                return shape.model_validate(extract_json(text))
            except (ValueError, ValidationError) as exc:
                logger.warning("teaching answer did not match %s (attempt %s): %s", shape.__name__, attempt, type(exc).__name__)
                messages += [HumanMessage(f"The JSON was not valid: {str(exc)[:400]}. Send the corrected JSON object only.")]
        raise BadAnswer(shape.__name__)

    def _meta(self, started: float, model_id: str | None = None) -> Meta:
        return Meta(prompt_version=prompts.PROMPT_VERSION, model_id=model_id or self.settings.llm_model,
                    latency_ms=int((time.perf_counter() - started) * 1000))

    # ----- the features ----------------------------------------------------------------------------------------
    async def video_links(self, body: VideoLinksRequest) -> VideoLinksResponse:
        started = time.perf_counter()
        system = prompts.VIDEO_LINKS.format(language=prompts.LANGUAGE[body.language])
        result = await self._structured(system, body.model_dump(exclude={"language"}), VideoLinksResponse)
        result.meta = self._meta(started)
        return result

    async def quick_check(self, body: QuickCheckRequest) -> QuickCheckResponse:
        started = time.perf_counter()
        system = prompts.QUICK_CHECK.format(count=body.count, language=prompts.LANGUAGE[body.language])
        result = await self._structured(system, {"title": body.title, "content": body.context}, QuickCheckResponse)
        result.questions = [q for q in result.questions if q.answer_index < len(q.options)][: body.count]
        if not result.questions:
            raise BadAnswer("QuickCheckResponse")
        result.meta = self._meta(started)
        return result

    async def ocr(self, body: OcrRequest) -> OcrResponse:
        if self.vision is None:
            raise BadAnswer("no vision model")
        started = time.perf_counter()
        message = HumanMessage(content=[
            {"type": "text", "text": prompts.OCR},
            {"type": "image_url", "image_url": {"url": f"data:{body.mime_type};base64,{body.image_base64}"}},
        ])
        text = str((await self.vision.ainvoke([message])).content).strip()
        if not text:
            raise BadAnswer("empty OCR")
        return OcrResponse(text=text, meta=self._meta(started, self.settings.vision_model))

    async def parse(self, body: ParseRequest) -> ParseResponse:
        started = time.perf_counter()
        result = await self._structured(prompts.PARSE, {"text": body.text}, ParseResponse)
        result.meta = self._meta(started)
        return result

    async def lesson(self, body: LessonRequest) -> LessonResponse:
        started = time.perf_counter()
        roles = f"استخدم في جملة التدريب مواقع من دي: {'، '.join(body.roles)}." if body.roles else ""
        system = prompts.LESSON.format(topic=body.topic_title, difficulty=body.difficulty, roles=roles)
        result = await self._structured(system, {"topic": body.topic_title}, LessonResponse)
        result.meta = self._meta(started)
        return result

    async def feedback(self, body: FeedbackRequest) -> FeedbackResponse:
        started = time.perf_counter()
        system = prompts.FEEDBACK.format(sentence=body.sentence, topic=body.topic_title)
        result = await self._structured(system, body.model_dump(), FeedbackResponse)
        result.meta = self._meta(started)
        return result
