"""Audit write API. All contexts record evidence through this service."""

from typing import Any

import structlog
from django.http import HttpRequest

from next_core.audit.models import AuditEvent
from next_core.platform.logging import logger
from next_core.tenancy.context import current_tenant

_MAX_PAYLOAD_KEYS = 50
_MAX_PAYLOAD_BYTES = 16_384


def _bounded_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    if len(payload) > _MAX_PAYLOAD_KEYS:
        raise ValueError("Audit payload exceeds the key-count bound.")
    # Cheap size bound; evidence stays small and never carries secrets or full documents.
    approx = sum(len(str(k)) + len(str(v)) for k, v in payload.items())
    if approx > _MAX_PAYLOAD_BYTES:
        raise ValueError("Audit payload exceeds the size bound.")
    return payload


def record_event(
    *,
    operation: str,
    resource_type: str,
    resource_id: str,
    actor: str,
    actor_type: str,
    payload: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> AuditEvent:
    """Persist one audit event for the current tenant (raises without tenant context)."""
    ctx = current_tenant()
    correlation_id = str(structlog.contextvars.get_contextvars().get("correlation_id", ""))
    source_ip: str | None = None
    user_agent = ""
    if request is not None:
        source_ip = request.META.get("REMOTE_ADDR") or None
        user_agent = request.headers.get("User-Agent", "")[:512]
        correlation_id = getattr(request, "correlation_id", correlation_id)

    event = AuditEvent(
        tenant_id=ctx.tenant_id,
        actor=actor,
        actor_type=actor_type,
        operation=operation,
        resource_type=resource_type,
        resource_id=resource_id,
        correlation_id=correlation_id,
        source_ip=source_ip,
        user_agent=user_agent,
        payload=_bounded_payload(payload),
    )
    event.save()
    logger.info(
        "audit.event.recorded",
        operation=operation,
        resource_type=resource_type,
        audit_event_id=str(event.id),
    )
    return event
