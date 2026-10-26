"""Teaching AI endpoints (contract in docs/teaching/API.md), part of the AI service app next to Discovery and the
assistant. Every call needs the backend's service token (RS256, audience teaching-ai).

    POST /v1/teaching/video-links        3-point summary of a track video and 3 ideas to link it to a school subject
    POST /v1/teaching/quick-check        multiple-choice questions about some content
    POST /v1/teaching/grammar/ocr        the Arabic text in a photo
    POST /v1/teaching/grammar/parse      إعراب of every sentence of a text, word by word
    POST /v1/teaching/grammar/lesson     a grammar topic in 3-4 points, 2 solved sentences, a new one to try
    POST /v1/teaching/grammar/feedback   what each mistake is, why, and questions that lead to the answer
    POST /v1/teaching/grammar/ask        a short answer to a student's question about a topic
    GET  /teaching/health                the models in use (no token)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import ErrorCode, error_body
from assistant.auth import Unauthenticated, verify

from .config import Settings, get_settings
from .fake import FakeTeachingAi
from .schemas import (
    AskRequest,
    AskResponse,
    FeedbackRequest,
    FeedbackResponse,
    LessonRequest,
    LessonResponse,
    OcrRequest,
    OcrResponse,
    ParseRequest,
    ParseResponse,
    QuickCheckRequest,
    QuickCheckResponse,
    VideoLinksRequest,
    VideoLinksResponse,
)
from .service import BadAnswer, LlmTeachingAi, TeachingAi, create_model

logger = logging.getLogger("teaching")
router = APIRouter(prefix="/v1/teaching", tags=["teaching"])
health_router = APIRouter(tags=["teaching"])
R = TypeVar("R")


def install(app: FastAPI, *, production: bool, fake_models: bool = False, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    updates: dict[str, Any] = {}
    if fake_models:
        updates["llm_model"] = "fake"
    if production and settings.auth_disabled:
        logger.error("TEACHING_AUTH_DISABLED is ignored in production")
        updates["auth_disabled"] = False
    app.state.teaching_settings = settings.model_copy(update=updates) if updates else settings
    app.include_router(router)
    app.include_router(health_router)


def current_settings(request: Request) -> Settings:
    return request.app.state.teaching_settings


def get_ai(request: Request) -> TeachingAi:
    """Created on the first call, so a missing provider key only makes these endpoints answer 503."""
    state = request.app.state
    if getattr(state, "teaching_ai", None) is None:
        s = current_settings(request)
        if s.llm_model == "fake":
            state.teaching_ai = FakeTeachingAi()
        else:
            fallback = create_model(s.llm_fallback_model, s) if s.llm_fallback_model else None
            vision = create_model(s.vision_model, s) if s.vision_model else None
            state.teaching_ai = LlmTeachingAi(s, create_model(s.llm_model, s), fallback, vision)
            if s.grammar_engine == "nahw":
                from .nahw.coach import NahwTeachingAi

                state.teaching_ai = NahwTeachingAi.from_env(state.teaching_ai)
    return state.teaching_ai


def service_token(request: Request) -> None:
    try:
        verify(request, current_settings(request))
    except Unauthenticated as exc:
        logger.warning("teaching rejected token: %s", exc)
        raise _Rejected() from exc


class _Rejected(Exception):
    pass


def _error(status: int, code: ErrorCode, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=error_body(code, message))


async def _run(request: Request, call: Callable[[TeachingAi], Awaitable[R]]) -> R | JSONResponse:
    try:
        ai = get_ai(request)
    except Exception as exc:
        logger.error("teaching model could not start: %s", type(exc).__name__)
        return _error(503, ErrorCode.PROVIDER_UNAVAILABLE, "The teaching AI could not start.")
    try:
        return await asyncio.wait_for(call(ai), timeout=current_settings(request).reply_timeout_seconds)
    except TimeoutError:
        return _error(504, ErrorCode.TIMEOUT, "The teaching AI took too long.")
    except BadAnswer as exc:
        logger.warning("teaching bad answer: %s", exc)
        return _error(503, ErrorCode.PROVIDER_UNAVAILABLE, "The teaching AI could not answer.")
    except Exception as exc:
        logger.warning("teaching provider error %s status=%s", type(exc).__name__, getattr(exc, "status_code", "-"))
        return _error(503, ErrorCode.PROVIDER_UNAVAILABLE,
                      f"The teaching AI is not available ({type(exc).__name__}, status {getattr(exc, 'status_code', '-')}).")


def _token(request: Request) -> JSONResponse | None:
    try:
        service_token(request)
    except _Rejected:
        response = _error(401, ErrorCode.UNAUTHENTICATED, "Invalid or missing service token.")
        response.headers["WWW-Authenticate"] = "Bearer"
        return response
    return None


@health_router.get("/teaching/health")
async def health(request: Request) -> dict:
    s = current_settings(request)
    return {"status": "ok", "model": s.llm_model, "vision_model": s.vision_model}


@router.post("/video-links", response_model=VideoLinksResponse)
async def video_links(body: VideoLinksRequest, request: Request):
    return _token(request) or await _run(request, lambda ai: ai.video_links(body))


@router.post("/quick-check", response_model=QuickCheckResponse)
async def quick_check(body: QuickCheckRequest, request: Request):
    return _token(request) or await _run(request, lambda ai: ai.quick_check(body))


@router.post("/grammar/ocr", response_model=OcrResponse)
async def ocr(body: OcrRequest, request: Request):
    return _token(request) or await _run(request, lambda ai: ai.ocr(body))


@router.post("/grammar/parse", response_model=ParseResponse)
async def parse(body: ParseRequest, request: Request):
    return _token(request) or await _run(request, lambda ai: ai.parse(body))


@router.post("/grammar/lesson", response_model=LessonResponse)
async def lesson(body: LessonRequest, request: Request):
    return _token(request) or await _run(request, lambda ai: ai.lesson(body))


@router.post("/grammar/feedback", response_model=FeedbackResponse)
async def feedback(body: FeedbackRequest, request: Request):
    return _token(request) or await _run(request, lambda ai: ai.feedback(body))


@router.post("/grammar/ask", response_model=AskResponse)
async def ask(body: AskRequest, request: Request):
    return _token(request) or await _run(request, lambda ai: ai.ask(body))
