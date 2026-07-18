"""Structured JSON logging and correlation-ID propagation.

Every log line is JSON with a ``correlation_id`` bound for the duration of the request.
Logs must never contain secrets, tokens, card data, or unnecessary PII
(see .claude/rules/security.md).
"""

import logging
import uuid
from collections.abc import Callable
from typing import Any

import structlog
from django.http import HttpRequest, HttpResponse

CORRELATION_HEADER = "X-Request-ID"
_MAX_CORRELATION_ID_LENGTH = 64


def build_logging_config(log_level: str) -> dict[str, Any]:
    """Django LOGGING dict routing stdlib logging through structlog's JSON renderer."""
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    structlog.contextvars.merge_contextvars,
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.JSONRenderer(),
                ],
                "foreign_pre_chain": [
                    structlog.stdlib.add_log_level,
                    structlog.stdlib.add_logger_name,
                    timestamper,
                ],
            }
        },
        "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
        "root": {"handlers": ["console"], "level": log_level},
        "loggers": {
            "django": {"level": log_level},
            "django.server": {"level": "WARNING"},
        },
    }


logger: structlog.stdlib.BoundLogger = structlog.get_logger("next_core")


def _sanitize_correlation_id(raw: str | None) -> str:
    """Accept a client-supplied ID only if it is short and printable; else generate one."""
    if raw and len(raw) <= _MAX_CORRELATION_ID_LENGTH and raw.isprintable():
        return raw
    return f"req_{uuid.uuid4().hex}"


class CorrelationIdMiddleware:
    """Bind a correlation ID to structlog contextvars and echo it on the response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        correlation_id = _sanitize_correlation_id(request.headers.get(CORRELATION_HEADER))
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        request.correlation_id = correlation_id  # type: ignore[attr-defined]
        try:
            response = self.get_response(request)
            response[CORRELATION_HEADER] = correlation_id
            return response
        finally:
            structlog.contextvars.unbind_contextvars("correlation_id")


__all__ = [
    "CORRELATION_HEADER",
    "CorrelationIdMiddleware",
    "build_logging_config",
    "logger",
]


_ = logging  # stdlib logging is configured via the dict above; import kept for clarity
