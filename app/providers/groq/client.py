"""Thin async HTTP client for the Groq (OpenAI-compatible) API.

This module is the ONLY place that talks to Groq over the network. It maps every
HTTP/transport failure to a provider exception and never logs request or
response bodies (they contain student content).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.logging import log_event
from app.providers.errors import (
    ProviderAuthError,
    ProviderBadOutput,
    ProviderRateLimited,
    ProviderRejected,
    ProviderServerError,
    ProviderTimeout,
)

logger = logging.getLogger(__name__)


class GroqHttpClient:
    def __init__(
        self, *, api_key: str, base_url: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "junior-hub-discovery-ai/1.0"},
            timeout=httpx.Timeout(10.0, connect=3.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------ chat
    async def chat_json(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_completion_tokens: int,
        reasoning_effort: str,
        timeout: float,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_completion_tokens,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        response = await self._send("chat/completions", timeout, json=payload)
        try:
            choice = response.json()["choices"][0]
            content = choice["message"].get("content") or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderBadOutput("malformed chat response") from None
        if not content.strip():
            raise ProviderBadOutput(f"empty completion (finish_reason={choice.get('finish_reason')})")
        return content

    # ------------------------------------------------------------------- stt
    async def transcribe(
        self,
        *,
        model: str,
        audio: bytes,
        filename: str,
        mime_type: str,
        language: str,
        timeout: float,
        prompt: str = "",
    ) -> str:
        data = {"model": model, "language": language, "response_format": "json", "temperature": "0"}
        if prompt:
            data["prompt"] = prompt
        response = await self._send(
            "audio/transcriptions",
            timeout,
            files={"file": (filename, audio, mime_type)},
            data=data,
        )
        try:
            return str(response.json()["text"])
        except (ValueError, KeyError, TypeError):
            raise ProviderBadOutput("malformed transcription response") from None

    # ------------------------------------------------------------------- tts
    async def speak(self, *, model: str, voice: str, text: str, timeout: float) -> bytes:
        response = await self._send(
            "audio/speech",
            timeout,
            json={"model": model, "voice": voice, "input": text, "response_format": "wav"},
        )
        if not response.content.startswith(b"RIFF"):
            raise ProviderBadOutput("speech response is not a WAV file")
        return response.content

    # ------------------------------------------------------------- internals
    async def _send(self, path: str, timeout: float, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.post(path, timeout=timeout, **kwargs)
        except httpx.TimeoutException:
            log_event(logger, logging.WARNING, "groq_timeout", path=path, timeout_s=timeout)
            raise ProviderTimeout(f"{path} timed out") from None
        except httpx.TransportError as exc:
            log_event(logger, logging.WARNING, "groq_network_error", path=path, error=type(exc).__name__)
            raise ProviderServerError(f"{path} network error: {type(exc).__name__}") from None
        if response.is_success:
            return response
        self._raise_for_error(path, response)
        raise AssertionError("unreachable")  # pragma: no cover

    @staticmethod
    def _raise_for_error(path: str, response: httpx.Response) -> None:
        status = response.status_code
        err_code = err_type = ""
        try:
            error = response.json().get("error", {})
            err_code, err_type = str(error.get("code", "")), str(error.get("type", ""))
        except (ValueError, AttributeError):
            pass
        # Only status + error identifiers are logged, never message bodies.
        log_event(
            logger,
            logging.WARNING,
            "groq_error",
            path=path,
            status=status,
            error_code=err_code,
            error_type=err_type,
            retry_after=response.headers.get("retry-after", ""),
            limit_tokens=response.headers.get("x-ratelimit-limit-tokens", ""),
            reset_tokens=response.headers.get("x-ratelimit-reset-tokens", ""),
        )
        if status in (401, 403):
            raise ProviderAuthError("Groq rejected the API key (check GROQ_API_KEY in .env)")
        if status == 429:
            try:
                retry_after = float(response.headers.get("retry-after", ""))
            except ValueError:
                retry_after = None
            raise ProviderRateLimited(f"{path} rate limited", retry_after)
        if err_code == "json_validate_failed":
            raise ProviderBadOutput("model produced invalid JSON")
        if status >= 500:
            raise ProviderServerError(f"{path} returned {status}")
        raise ProviderRejected(f"{path} rejected the request ({status} {err_code})".strip())
