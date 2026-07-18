"""Telemetry bootstrap must be a strict no-op without an OTLP endpoint (air-gap rule)."""

import next_core.platform.telemetry as telemetry


def test_setup_is_noop_without_endpoint(monkeypatch: object) -> None:
    import pytest

    mp = monkeypatch
    assert isinstance(mp, pytest.MonkeyPatch)
    mp.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    mp.setattr(telemetry, "_initialized", False)
    assert telemetry.setup_telemetry() is False

    mp.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "   ")
    assert telemetry.setup_telemetry() is False
