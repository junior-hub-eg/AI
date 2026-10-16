"""Tiny HTTP client for the Discovery AI service (used by the Streamlit playground)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ApiResult:
    status: int  # 0 = could not connect
    body: Any
    seconds: float
    request_id: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == 200


class DiscoveryApi:
    def __init__(self, base_url: str, token: str = "", timeout: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token.strip()
        self._timeout = timeout

    def get(self, path: str) -> ApiResult:
        return self._send("GET", path, None, with_token=False)

    def post(self, path: str, payload: Any, *, with_token: bool = True) -> ApiResult:
        return self._send("POST", path, payload, with_token=with_token)

    def _send(self, method: str, path: str, payload: Any, *, with_token: bool) -> ApiResult:
        headers = {"Authorization": f"Bearer {self._token}"} if with_token and self._token else {}
        started = time.perf_counter()
        try:
            response = httpx.request(
                method, self._base_url + path, json=payload, headers=headers, timeout=self._timeout
            )
        except httpx.ConnectError:
            return ApiResult(
                0,
                None,
                time.perf_counter() - started,
                error=f"Cannot connect to {self._base_url}. Is the service running?",
            )
        except httpx.TimeoutException:
            return ApiResult(
                0, None, time.perf_counter() - started, error=f"No answer within {self._timeout:.0f} s"
            )
        try:
            body: Any = response.json()
        except ValueError:
            body = response.text
        return ApiResult(
            response.status_code,
            body,
            time.perf_counter() - started,
            request_id=response.headers.get("x-request-id"),
        )
