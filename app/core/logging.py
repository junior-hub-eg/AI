"""Structured JSON logging.

Rule: log metadata only (ids, models, latencies, error codes). Never log
audio, transcripts, questions or any other student content.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any

from app.core.context import request_id_ctx


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class RecentLogs(logging.Handler):
    """Keeps the last N log events in memory for the local debug panel (never used in production)."""

    def __init__(self, size: int = 400) -> None:
        super().__init__()
        self._items: deque[dict[str, Any]] = deque(maxlen=size)
        self._seq = 0
        self._lock = threading.Lock()
        self._fmt = JsonFormatter()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = json.loads(self._fmt.format(record))
        except Exception:  # pragma: no cover - never break logging
            return
        with self._lock:
            self._seq += 1
            payload["seq"] = self._seq
            self._items.append(payload)

    def since(self, after: int) -> list[dict[str, Any]]:
        with self._lock:
            return [item for item in self._items if item["seq"] > after]


recent_logs = RecentLogs()


def configure_logging(level: str = "INFO", *, keep_recent: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler, recent_logs] if keep_recent else [handler]
    root.setLevel(level.upper())
    logging.getLogger("httpx").setLevel(logging.WARNING)


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    logger.log(level, event, extra={"fields": fields})
