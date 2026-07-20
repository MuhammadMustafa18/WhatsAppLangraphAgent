"""Structured logging via structlog.

Provides:
  - JSON output in production, pretty console in development.
  - Request-context middleware that injects request_id into every log event.
  - Redaction processor (seeded here, expanded in later steps).
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from structlog.contextvars import merge_contextvars, bind_contextvars, unbind_contextvars

from app.core.config import get_settings


def _redaction_processor(
    _logger: structlog.stdlib.BoundLogger,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Scrub known-sensitive fields before they hit the output.

    This runs inside the structlog pipeline — before serialization —
    so even accidentally-logged secrets are redacted.
    """
    REDACTED = "[REDACTED]"
    SENSITIVE_KEYS = {
        "api_key", "apikey", "api-key",
        "password", "passwd", "secret", "token", "authorization",
        "jwt", "encryption_key", "private_key",
    }
    for key in SENSITIVE_KEYS:
        if key in event_dict:
            event_dict[key] = REDACTED
    return event_dict


log_buffer: deque[dict[str, Any]] = deque(maxlen=2000)


def _log_buffer_processor(
    _logger: structlog.stdlib.BoundLogger,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    log_buffer.append(event_dict.copy())
    return event_dict


def configure_logging() -> None:
    """Call once at app startup to replace stdlib logging with structlog.

    Dev:    colorful console output (LOG_FORMAT=dev or unset).
    Prod:   line-delimited JSON (LOG_FORMAT=json).
    """
    settings = get_settings()
    is_dev = settings.LOG_FORMAT != "json"

    shared_processors: list[structlog.types.Processor] = [
        merge_contextvars,
        _redaction_processor,
        structlog.processors.add_log_level,
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _log_buffer_processor,
    ]

    if is_dev:
        shared_processors.append(
            structlog.dev.ConsoleRenderer(
                colors=True,
                sort_keys=False,
            ),
        )
    else:
        shared_processors.append(
            structlog.processors.JSONRenderer(),
        )

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route stdlib loggers from third-party libs through structlog too.
    logging.basicConfig(
        format="%(message)s",
        level=settings.LOG_LEVEL.upper(),
        force=True,
        handlers=[logging.StreamHandler()],
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Shortcut: structlog.get_logger that returns our wrapper type."""
    return structlog.get_logger(name or __name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that injects request_id into every log line.

    Generates a UUID per request, binds it to structlog contextvars,
    and adds it to the response headers (X-Request-ID).
    Cleans up context after the response is sent.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        unbind_contextvars("request_id")
        return response
