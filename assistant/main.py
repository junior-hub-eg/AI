"""Junior Hub Student Assistant: HTTP API (contract in docs/API.md).

Run: uvicorn app.main:app --port 8010      Interactive docs: http://localhost:8010/docs
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .assistant import Assistant, EmptyReply
from .auth import Unauthenticated, verify
from .catalog import load_catalog
from .config import get_settings
from .llm import create_model
from .schemas import MAX_HISTORY, MAX_MESSAGE, HistoryItem, ReplyRequest, ReplyResponse

logger = logging.getLogger("assistant")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

PERSONAS = Path(__file__).resolve().parent.parent / "mock" / "contexts"
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Junior Hub Student Assistant",
    version="1.0",
    description=(
        "Answers a student's questions about their own Junior Hub journey. Stateless: the caller (the Junior Hub "
        "backend) stores the conversation and sends the history and the student's context with every message. "
        "See docs/API.md and docs/INTEGRATION.md."
    ),
)


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


def current_settings():
    """The settings in use, without building the model (so the test page opens even when the model cannot start)."""
    return app.state.assistant.settings if hasattr(app.state, "assistant") else get_settings()


def get_assistant() -> Assistant:
    if not hasattr(app.state, "assistant"):
        settings = get_settings()
        if settings.auth_disabled:
            logger.warning("AUTH_DISABLED=true: anyone can call the service. For local testing only.")
        if settings.dev_endpoints:
            logger.warning("DEV_ENDPOINTS=true: /v1/dev/* is open. For local testing only.")
        app.state.assistant = Assistant(create_model(settings), settings)
    return app.state.assistant


def request_id_of(request: Request) -> str:
    return request.headers.get("x-request-id") or uuid.uuid4().hex


def _error_text(exc: Exception) -> str:
    """The provider's own error message, without the HTTP headers some SDKs put first (dev endpoints only)."""
    body = getattr(exc, "body", None)
    if body is not None:
        return (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, default=str))[:600]
    return str(exc)[:600]


def error(status: int, code: str, message: str, request_id: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "request_id": request_id}})


def service_token(request: Request) -> None:
    """Runs before the body is validated, so a caller without a valid token learns nothing about the schema."""
    verify(request, current_settings())


@app.exception_handler(Unauthenticated)
async def unauthenticated(request: Request, exc: Unauthenticated) -> JSONResponse:
    logger.warning("rejected token: %s", exc)
    return error(401, "UNAUTHENTICATED", "Invalid or missing service token.", request_id_of(request))


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Field names only: the student's message is never logged or echoed.
    fields = sorted({".".join(str(p) for p in e["loc"][1:]) or "body" for e in exc.errors()})
    return error(400, "INVALID_REQUEST", f"Invalid fields: {', '.join(fields)}", request_id_of(request))


async def run_reply(body: ReplyRequest, request_id: str, debug: bool = False) -> ReplyResponse | JSONResponse:
    """The reply, or an error body. With `debug` (dev endpoints only) the tools used and the provider's error are
    included, to see why the bot answered what it did."""
    try:
        assistant = get_assistant()
    except Exception as exc:  # the model could not be created: a missing key or provider package
        logger.error("model could not start: %s", type(exc).__name__)
        detail = f" {type(exc).__name__}: {_error_text(exc)}" if debug else ""
        return error(503, "PROVIDER_UNAVAILABLE", "The assistant's model could not start." + detail, request_id)
    try:
        response, trace = await asyncio.wait_for(assistant.reply_with_trace(body), timeout=assistant.settings.reply_timeout_seconds)
        tools = [step["tool"] for step in trace["steps"]]
    except asyncio.TimeoutError:
        logger.warning("reply timed out request_id=%s", request_id)
        return error(504, "TIMEOUT", "The assistant took too long.", request_id)
    except EmptyReply:
        logger.warning("empty reply request_id=%s", request_id)
        return error(503, "PROVIDER_UNAVAILABLE", "The assistant could not answer.", request_id)
    except Exception as exc:  # the model provider failed
        logger.warning("provider error %s request_id=%s", type(exc).__name__, request_id)
        detail = f" {type(exc).__name__}: {_error_text(exc)}" if debug else ""
        return error(503, "PROVIDER_UNAVAILABLE", "The assistant is not available right now." + detail, request_id)

    logger.info("reply request_id=%s prompt=%s model=%s latency_ms=%s topic=%s tools=%s",
                request_id, response.meta.prompt_version, response.meta.model_id, response.meta.latency_ms,
                response.topic, ",".join(tools) or "-")
    if debug:
        return JSONResponse({**response.model_dump(mode="json"), "debug": {"tools": tools, **trace}})
    return response


@app.get("/", include_in_schema=False)
async def home():
    """The test chat page with DEV_ENDPOINTS=true; otherwise where to look."""
    if current_settings().dev_endpoints:
        return FileResponse(STATIC / "playground.html", media_type="text/html; charset=utf-8")
    return {"service": "Junior Hub Student Assistant", "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["service"])
async def health() -> dict:
    """Liveness, the model in use and the catalog version. No token needed."""
    return {"status": "ok", "model": current_settings().llm_model, "catalog_version": load_catalog().version}


@app.post("/v1/assistant/replies", response_model=ReplyResponse, responses=ERRORS, tags=["assistant"],
          dependencies=[Depends(service_token)])
async def replies(body: ReplyRequest, request: Request):
    """Reply to one student message. Send the recent history and the student's context with every call."""
    return await run_reply(body, request_id_of(request))


# ----- Development only: try the bot with the mock students, without building a context -------------------------

class DevChatRequest(BaseModel):
    persona: str = Field(examples=["frontend_beginner"])
    message: str = Field(min_length=1, max_length=MAX_MESSAGE, examples=["الدرس الجاي إيه؟"])
    history: list[HistoryItem] = Field(default_factory=list, max_length=MAX_HISTORY)


def dev_only() -> None:
    if not current_settings().dev_endpoints:
        raise HTTPException(status_code=404)


def load_persona(name: str) -> dict:
    path = PERSONAS / f"{name}.json"
    if path.parent != PERSONAS or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Unknown persona. Try one of: {', '.join(personas())}")
    return json.loads(path.read_text(encoding="utf-8"))


def personas() -> list[str]:
    return sorted(p.stem for p in PERSONAS.glob("*.json"))


@app.get("/v1/dev/personas", tags=["development"], dependencies=[Depends(dev_only)])
async def list_personas() -> list[str]:
    """The mock students (DEV_ENDPOINTS=true only)."""
    return personas()


@app.get("/v1/dev/personas/{name}", tags=["development"], dependencies=[Depends(dev_only)])
async def get_persona(name: str) -> dict:
    """A mock student's context, as the backend would send it (DEV_ENDPOINTS=true only)."""
    return load_persona(name)


@app.post("/v1/dev/chat", response_model=ReplyResponse, responses=ERRORS, tags=["development"], dependencies=[Depends(dev_only)])
async def dev_chat(body: DevChatRequest, request: Request):
    """Chat as a mock student, no token or context needed (DEV_ENDPOINTS=true only)."""
    reply_request = ReplyRequest(conversation_id=uuid.uuid4(), student_ref=uuid.uuid4(), message=body.message,
                                 history=body.history, context=load_persona(body.persona))
    return await run_reply(reply_request, request_id_of(request), debug=True)
