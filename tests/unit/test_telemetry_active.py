"""Telemetry bootstrap with an endpoint configured (no network traffic is emitted)."""

import pytest

import next_core.platform.telemetry as telemetry


def test_setup_activates_and_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    from opentelemetry.instrumentation.django import DjangoInstrumentor

    monkeypatch.setattr(telemetry, "_initialized", False)
    # Dead local port: exporter construction is lazy, nothing is sent during the test.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9/v1/traces")
    try:
        assert telemetry.setup_telemetry() is True
        # Second call is a cheap no-op once initialized.
        assert telemetry.setup_telemetry() is True
    finally:
        DjangoInstrumentor().uninstrument()
