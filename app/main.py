"""Application factory.

Run with:  uvicorn app.main:create_app --factory --port 8000
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import health
from app.api.v1 import discovery
from app.container import Container, build_container
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, log_event
from app.core.middleware import RequestContextMiddleware

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    production = settings.app_env == "production"

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
        )
        yield
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
    return app
