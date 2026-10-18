"""Application factory.

Run with:  uvicorn app.main:create_app --factory --port 8000
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import health
from app.api.v1 import discovery
from app.container import Container, build_container
from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, log_event, recent_logs
from app.core.middleware import RequestContextMiddleware

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    production = settings.app_env == "production"
    configure_logging(settings.log_level, keep_recent=not production)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = active = container or build_container(settings)
        log_event(
            logger,
            logging.INFO,
            "service_started",
            env=settings.app_env,
            fake_models=settings.fake_models,
            auth_disabled=settings.auth_disabled,
            turn_model=settings.llm_turn_model,
            result_model=settings.llm_result_model,
            stt_model=settings.stt_model,
            tts_model=settings.tts_model,
            language=settings.interview_language,
        )
        # Prepare question 1's audio in the background (never blocks startup).
        warm = None if settings.fake_models else asyncio.create_task(active.turn_service.warm_up())
        yield
        if warm and not warm.done():
            warm.cancel()
        await active.aclose()

    app = FastAPI(
        title="Junior Hub Discovery AI",
        version=__version__,
        description="Stateless AI service behind the Track Discovery interview.",
        lifespan=lifespan,
        docs_url=None if production else "/docs",
        redoc_url=None,
        openapi_url=None if production else "/openapi.json",
    )
    app.add_middleware(RequestContextMiddleware, max_request_bytes=settings.max_request_bytes)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(discovery.router)
    web_dir = PROJECT_ROOT / "web"
    if not production and web_dir.is_dir():
        # Call-style interview page for local demos: http://127.0.0.1:<port>/call/
        app.mount("/call", StaticFiles(directory=web_dir, html=True), name="call")

        @app.get("/call-config", include_in_schema=False)
        async def _call_config() -> dict[str, object]:
            # Lets the call page match the interview language (ar = RTL Arabic UI, en = English UI).
            return {"language": settings.interview_language}

        @app.get("/debug/logs", include_in_schema=False)
        async def _debug_logs(after: int = 0) -> dict[str, object]:
            # Local debugging only: the last server log events (metadata, no student content).
            return {"items": recent_logs.since(after)}

        @app.get("/", include_in_schema=False)
        async def _root() -> RedirectResponse:
            return RedirectResponse("/call/")

    return app
