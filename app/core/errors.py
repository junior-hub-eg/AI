"""Application errors and the JSON error envelope returned to the backend."""

from __future__ import annotations

import logging
from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import request_id_ctx

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    INVALID_REQUEST = "INVALID_REQUEST"
    AUDIO_UNSUPPORTED = "AUDIO_UNSUPPORTED"
    AUDIO_TOO_LARGE = "AUDIO_TOO_LARGE"
    # Not in the SRS table: speech was received but nothing could be understood.
    AUDIO_UNINTELLIGIBLE = "AUDIO_UNINTELLIGIBLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """An error that maps to a specific HTTP status and error code."""

    status_code = 500
    code = ErrorCode.INTERNAL_ERROR

    def __init__(
        self, message: str, *, code: ErrorCode | None = None, status_code: int | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class Unauthenticated(AppError):
    status_code, code = 401, ErrorCode.UNAUTHENTICATED

    def __init__(self, message: str = "Missing or invalid service token") -> None:
        super().__init__(message)


class InvalidRequest(AppError):
    status_code, code = 400, ErrorCode.INVALID_REQUEST


class AudioUnsupported(AppError):
    status_code, code = 415, ErrorCode.AUDIO_UNSUPPORTED


class AudioTooLarge(AppError):
    status_code, code = 413, ErrorCode.AUDIO_TOO_LARGE


class AudioUnintelligible(AppError):
    status_code, code = 422, ErrorCode.AUDIO_UNINTELLIGIBLE


class ProviderUnavailable(AppError):
    status_code, code = 503, ErrorCode.PROVIDER_UNAVAILABLE


class DeadlineExceeded(AppError):
    status_code, code = 504, ErrorCode.TIMEOUT


def error_body(code: ErrorCode | str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": str(code), "message": message, "request_id": request_id_ctx.get()}}


def error_response(exc: AppError, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(error_body(exc.code, exc.message), status_code=exc.status_code, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return error_response(exc, headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Only field paths and rules are reported, never submitted values
        # (they may contain student answers).
        problems = [f"{'.'.join(str(p) for p in e['loc'] if p != 'body')}: {e['msg']}" for e in exc.errors()][
            :5
        ]
        return JSONResponse(
            error_body(ErrorCode.INVALID_REQUEST, "; ".join(problems) or "Invalid request"),
            status_code=400,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            error_body(ErrorCode.INVALID_REQUEST, str(exc.detail)), status_code=exc.status_code
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_exception", exc_info=exc)
        return JSONResponse(error_body(ErrorCode.INTERNAL_ERROR, "Internal error"), status_code=500)
