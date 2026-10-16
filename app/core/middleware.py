"""Request id, request-size guard and access log."""

from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import request_id_ctx
from app.core.errors import AudioTooLarge, ErrorCode, error_body, error_response
from app.core.logging import log_event

logger = logging.getLogger("app.access")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_request_bytes: int) -> None:
        super().__init__(app)
        self._max_bytes = max_request_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid4().hex
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > self._max_bytes:
                response: Response = error_response(AudioTooLarge("Request body is too large"))
            else:
                response = await call_next(request)
        except Exception:
            logger.exception("request_failed")
            response = JSONResponse(error_body(ErrorCode.INTERNAL_ERROR, "Internal error"), status_code=500)
        response.headers["X-Request-Id"] = request_id
        log_event(
            logger,
            logging.INFO,
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        request_id_ctx.reset(token)
        return response
