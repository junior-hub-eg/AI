"""Junior Hub Student Assistant: the HTTP endpoints (contract in docs/assistant/API.md).

They are part of the AI service app (`app.main.create_app` calls `install`), next to the Discovery endpoints:

    POST /v1/assistant/replies      the backend's call (service token, audience assistant-ai)
    GET  /assistant/health          the model in use and the catalog version (no token)
    GET  /assistant/                the test chat page            } ASSISTANT_DEV_ENDPOINTS=true only,
    /v1/dev/personas, /v1/dev/chat  chat as a mock student        } never in production
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.core.errors import ErrorCode, error_body

from .assistant import Assistant, EmptyReply
from .auth import Unauthenticated, verify
from .catalog import load_catalog
from .config import Settings, get_settings
from .llm import create_model
from .schemas import MAX_HISTORY, MAX_MESSAGE, HistoryItem, ReplyRequest, ReplyResponse

logger = logging.getLogger("assistant")

PERSONAS = Path(__file__).resolve().parent / "mock" / "contexts"
STATIC = Path(__file__).resolve().parent / "static"

router = APIRouter()


class ErrorBody(BaseModel):
    code: str = Field(examples=["UNAUTHENTICATED"])
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "INVALID_REQUEST: a field is missing or out of range"},
    401: {"model": ErrorResponse, "description": "UNAUTHENTICATED: missing, expired or wrongly signed service token"},
    503: {"model": ErrorResponse, "description": "PROVIDER_UNAVAILABLE: the model failed; show your fallback reply"},
    504: {"model": ErrorResponse, "description": "TIMEOUT: no reply in time; show your fallback reply"},
}


def install(app: FastAPI, *, production: bool, fake_models: bool = False, settings: Settings | None = None) -> None:
    """Adds the assistant to the AI service app. The model is created on the first message, so a missing provider
    key or package only makes the assistant answer 503 and never stops the Discovery endpoints."""
    settings = settings or get_settings()
    updates: dict[str, Any] = {}
    if fake_models:
        updates["llm_model"] = "fake"
    if production and (settings.auth_disabled or settings.dev_endpoints):
        logger.error("ASSISTANT_AUTH_DISABLED and ASSISTANT_DEV_ENDPOINTS are ignored in production")
        updates |= {"auth_disabled": False, "dev_endpoints": False}
    app.state.assistant_settings = settings.model_copy(update=updates) if updates else settings
    if app.state.assistant_settings.auth_disabled:
        logger.warning("ASSISTANT_AUTH_DISABLED=true: anyone can call the assistant. For local testing only.")
    if app.state.assistant_settings.dev_endpoints:
        logger.warning("ASSISTANT_DEV_ENDPOINTS=true: /v1/dev/* is open. For local testing only.")

    app.add_exception_handler(Unauthenticated, _unauthenticated)
    app.include_router(router)


def current_settings(request: Request) -> Settings:
    return request.app.state.assistant_settings


def get_assistant(request: Request) -> Assistant:
    state = request.app.state
    if getattr(state, "assistant", None) is None:
        settings = current_settings(request)
        state.assistant = Assistant(create_model(settings), settings)
    return state.assistant


def _error_text(exc: Exception) -> str:
    """The provider's own error message, without the HTTP headers some SDKs put first (dev endpoints only)."""
    body = getattr(exc, "body", None)
    if body is not None:
        return (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, default=str))[:600]
    return str(exc)[:600]


def error(status: int, code: ErrorCode, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=error_body(code, message))


def service_token(request: Request) -> None:
    """Runs before the body is validated, so a caller without a valid token learns nothing about the schema."""
    verify(request, current_settings(request))


async def _unauthenticated(request: Request, exc: Exception) -> JSONResponse:
    logger.warning("assistant rejected token: %s", exc)
    response = error(401, ErrorCode.UNAUTHENTICATED, "Invalid or missing service token.")
    response.headers["WWW-Authenticate"] = "Bearer"
    return response


async def run_reply(request: Request, body: ReplyRequest, debug: bool = False) -> ReplyResponse | JSONResponse:
    """The reply, or an error body. With `debug` (dev endpoints only) the tools used and the provider's error are
    included, to see why the bot answered what it did."""
    try:
        assistant = get_assistant(request)
    except Exception as exc:  # the model could not be created: a missing key or provider package
        logger.error("assistant model could not start: %s", type(exc).__name__)
        detail = f" {type(exc).__name__}: {_error_text(exc)}" if debug else ""
        return error(503, ErrorCode.PROVIDER_UNAVAILABLE, "The assistant's model could not start." + detail)
    try:
        response, trace = await asyncio.wait_for(
            assistant.reply_with_trace(body), timeout=assistant.settings.reply_timeout_seconds
        )
        tools = [step["tool"] for step in trace["steps"]]
    except TimeoutError:
        logger.warning("assistant reply timed out")
        return error(504, ErrorCode.TIMEOUT, "The assistant took too long.")
    except EmptyReply:
        logger.warning("assistant empty reply")
        return error(503, ErrorCode.PROVIDER_UNAVAILABLE, "The assistant could not answer.")
    except Exception as exc:  # the model provider failed
        # The provider's status helps tell a retired model (404) from a bad key (401) or a quota limit (429).
        logger.warning("assistant provider error %s status=%s", type(exc).__name__, getattr(exc, "status_code", "-"))
        detail = f" {type(exc).__name__}: {_error_text(exc)}" if debug else ""
        return error(503, ErrorCode.PROVIDER_UNAVAILABLE, "The assistant is not available right now." + detail)

    # Never the message or the reply (privacy): metadata only.
    logger.info(
        "assistant reply prompt=%s model=%s latency_ms=%s topic=%s tools=%s",
        response.meta.prompt_version, response.meta.model_id, response.meta.latency_ms,
        response.topic, ",".join(tools) or "-",
    )
    if debug:
        return JSONResponse({**response.model_dump(mode="json"), "debug": {"tools": tools, **trace}})
    return response


@router.get("/assistant/health", tags=["assistant"])
async def health(request: Request) -> dict:
    """Liveness, the model in use and the catalog version. No token needed, no model call."""
    return {"status": "ok", "model": current_settings(request).llm_model, "catalog_version": load_catalog().version}


@router.post(
    "/v1/assistant/replies", response_model=ReplyResponse, responses=ERRORS, tags=["assistant"],
    dependencies=[Depends(service_token)],
)
async def replies(body: ReplyRequest, request: Request):
    """Reply to one student message. Send the recent history and the student's context with every call."""
    return await run_reply(request, body)


# ----- Development only: try the bot with the mock students, without building a context -------------------------

class DevChatRequest(BaseModel):
    persona: str = Field(examples=["frontend_beginner"])
    message: str = Field(min_length=1, max_length=MAX_MESSAGE, examples=["الدرس الجاي إيه؟"])
    history: list[HistoryItem] = Field(default_factory=list, max_length=MAX_HISTORY)


def dev_only(request: Request) -> None:
    if not current_settings(request).dev_endpoints:
        raise HTTPException(status_code=404, detail="Not Found")


def load_persona(name: str) -> dict:
    path = PERSONAS / f"{name}.json"
    if path.parent != PERSONAS or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Unknown persona. Try one of: {', '.join(personas())}")
    return json.loads(path.read_text(encoding="utf-8"))


def personas() -> list[str]:
    return sorted(p.stem for p in PERSONAS.glob("*.json"))


@router.get("/assistant/", include_in_schema=False, dependencies=[Depends(dev_only)])
async def test_page():
    """The test chat page (ASSISTANT_DEV_ENDPOINTS=true only)."""
    return FileResponse(STATIC / "playground.html", media_type="text/html; charset=utf-8")


@router.get("/v1/dev/personas", tags=["development"], dependencies=[Depends(dev_only)])
async def list_personas() -> list[str]:
    """The mock students (ASSISTANT_DEV_ENDPOINTS=true only)."""
    return personas()


@router.get("/v1/dev/personas/{name}", tags=["development"], dependencies=[Depends(dev_only)])
async def get_persona(name: str) -> dict:
    """A mock student's context, as the backend would send it (ASSISTANT_DEV_ENDPOINTS=true only)."""
    return load_persona(name)


@router.post(
    "/v1/dev/chat", response_model=ReplyResponse, responses=ERRORS, tags=["development"],
    dependencies=[Depends(dev_only)],
)
async def dev_chat(body: DevChatRequest, request: Request):
    """Chat as a mock student, no token or context needed (ASSISTANT_DEV_ENDPOINTS=true only)."""
    reply_request = ReplyRequest(
        conversation_id=uuid.uuid4(), student_ref=uuid.uuid4(), message=body.message,
        history=body.history, context=load_persona(body.persona),
    )
    return await run_reply(request, reply_request, debug=True)
