"""Groq chat provider with repair and model fallback."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import log_event
from app.providers.base import LlmResult, LlmTask, Message, T
from app.providers.errors import (
    ProviderAuthError,
    ProviderBadOutput,
    ProviderError,
    ProviderExhausted,
)
from app.providers.groq.client import GroqHttpClient

logger = logging.getLogger(__name__)
_ATTEMPTS_PER_MODEL = 2  # first try + one repair/retry


@dataclass(frozen=True)
class Route:
    models: tuple[str, ...]
    temperature: float
    max_tokens: int
    reasoning_effort: str
    timeout: float


class GroqLlm:
    def __init__(self, client: GroqHttpClient, settings: Settings) -> None:
        self._client = client
        self._routes = {
            LlmTask.TURN: self._route(
                settings.llm_turn_model,
                settings.llm_turn_fallback_model,
                settings.llm_turn_temperature,
                settings.llm_turn_max_tokens,
                settings.llm_turn_reasoning_effort,
                settings.llm_turn_timeout_seconds,
            ),
            LlmTask.RESULT: self._route(
                settings.llm_result_model,
                settings.llm_result_fallback_model,
                settings.llm_result_temperature,
                settings.llm_result_max_tokens,
                settings.llm_result_reasoning_effort,
                settings.llm_result_timeout_seconds,
            ),
        }

    @staticmethod
    def _route(
        primary: str, fallback: str | None, temperature: float, max_tokens: int, effort: str, timeout: float
    ) -> Route:
        models = (primary,) if not fallback or fallback == primary else (primary, fallback)
        return Route(models, temperature, max_tokens, effort, timeout)

    async def generate_json(
        self,
        *,
        task: LlmTask,
        messages: list[Message],
        parse: Callable[[dict[str, Any]], T],
        context: Mapping[str, Any] | None = None,
    ) -> LlmResult[T]:
        route = self._routes[task]
        for model in route.models:
            conversation = list(messages)
            for attempt in range(1, _ATTEMPTS_PER_MODEL + 1):
                try:
                    raw = await self._client.chat_json(
                        model=model,
                        messages=conversation,
                        temperature=route.temperature,
                        max_completion_tokens=route.max_tokens,
                        reasoning_effort=route.reasoning_effort,
                        timeout=route.timeout,
                    )
                except ProviderAuthError:
                    raise
                except ProviderBadOutput as exc:
                    self._log(task, model, attempt, "bad_output", exc)
                    continue  # retry the same model once
                except ProviderError as exc:
                    self._log(task, model, attempt, type(exc).__name__, exc)
                    break  # go straight to the next model
                try:
                    return LlmResult(parse(_load_json(raw)), model)
                except (ValueError, KeyError, TypeError) as exc:
                    reason = _describe(exc)
                    self._log(task, model, attempt, "invalid_output", reason)
                    conversation = [
                        *messages,
                        {"role": "assistant", "content": raw},
                        {
                            "role": "user",
                            "content": (
                                f"Your previous reply could not be used: {reason}. "
                                "Reply again with ONLY the corrected JSON object, "
                                "no code fences and no commentary."
                            ),
                        },
                    ]
        raise ProviderExhausted("all configured models failed")

    @staticmethod
    def _log(task: LlmTask, model: str, attempt: int, reason: str, detail: object) -> None:
        log_event(
            logger,
            logging.WARNING,
            "llm_attempt_failed",
            task=task.value,
            model=model,
            attempt=attempt,
            reason=reason,
            detail=str(detail)[:200],
        )


def _load_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("the reply is not a JSON object")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("the reply is not a JSON object")
    return data


def _describe(exc: Exception) -> str:
    """Explain a failure to the model WITHOUT echoing any content."""
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:4])
    if isinstance(exc, json.JSONDecodeError):
        return "the reply is not valid JSON"
    if isinstance(exc, KeyError):
        return f"missing key {exc}"
    return re.sub(r"\s+", " ", str(exc))[:200] or type(exc).__name__
