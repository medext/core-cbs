"""Unit tests for structured logging and correlation-ID middleware (no database)."""

import uuid

from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

from next_core.platform.logging import (
    CORRELATION_HEADER,
    CorrelationIdMiddleware,
    _sanitize_correlation_id,
)


def _passthrough(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


class TestSanitizeCorrelationId:
    def test_generates_id_when_absent(self) -> None:
        generated = _sanitize_correlation_id(None)
        assert generated.startswith("req_")
        assert len(generated) == 4 + 32

    def test_keeps_valid_client_id(self) -> None:
        client_id = f"client-{uuid.uuid4()}"
        assert _sanitize_correlation_id(client_id) == client_id

    def test_rejects_oversized_id(self) -> None:
        oversized = "x" * 65
        assert _sanitize_correlation_id(oversized) != oversized

    def test_rejects_non_printable_id(self) -> None:
        hostile = "abc\r\nInjected-Header: 1"
        assert _sanitize_correlation_id(hostile) != hostile


class TestCorrelationIdMiddleware:
    def test_response_carries_generated_id(self) -> None:
        middleware = CorrelationIdMiddleware(_passthrough)
        response = middleware(RequestFactory().get("/health/live"))
        assert response[CORRELATION_HEADER].startswith("req_")

    def test_client_supplied_id_is_echoed(self) -> None:
        middleware = CorrelationIdMiddleware(_passthrough)
        request = RequestFactory().get("/health/live", headers={CORRELATION_HEADER: "my-id-123"})
        response = middleware(request)
        assert response[CORRELATION_HEADER] == "my-id-123"

    def test_request_object_gets_correlation_id(self) -> None:
        captured: dict[str, str] = {}

        def capture(request: HttpRequest) -> HttpResponse:
            captured["cid"] = request.correlation_id  # type: ignore[attr-defined]
            return HttpResponse("ok")

        CorrelationIdMiddleware(capture)(RequestFactory().get("/"))
        assert captured["cid"].startswith("req_")
