"""Translate provider failures into the API error codes the backend understands."""

from __future__ import annotations

from app.core.errors import AppError, DeadlineExceeded, ProviderUnavailable
from app.providers.errors import ProviderError, ProviderTimeout


def to_app_error(exc: ProviderError) -> AppError:
    if isinstance(exc, ProviderTimeout):
        return DeadlineExceeded("The AI provider timed out")
    return ProviderUnavailable("The AI provider is unavailable")
