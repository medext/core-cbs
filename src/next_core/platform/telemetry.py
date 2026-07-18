"""OpenTelemetry bootstrap.

No-op unless OTEL_EXPORTER_OTLP_ENDPOINT is set, so local dev and air-gapped installs run
without any telemetry backend. Called once from wsgi/asgi entry points.
"""

import os

_initialized = False


def setup_telemetry() -> bool:
    """Initialize tracing if an OTLP endpoint is configured. Returns True if active."""
    global _initialized
    if _initialized:
        return True

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return False

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.django import DjangoInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "next-core")})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    DjangoInstrumentor().instrument()

    _initialized = True
    return True
