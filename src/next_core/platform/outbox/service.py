"""Outbox write + relay services."""

from collections.abc import Callable
from typing import Any

import structlog
from django.db import connections, transaction

from next_core.platform.clock import now
from next_core.platform.logging import logger
from next_core.platform.outbox.models import OutboxEvent, OutboxStatus
from next_core.tenancy.context import current_tenant

MAX_ATTEMPTS = 10


def emit(
    event_type: str,
    *,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
    version: int = 1,
) -> OutboxEvent:
    """Record a domain event. MUST be called inside the business DB transaction."""
    ctx = current_tenant()
    if not connections[ctx.db_alias].in_atomic_block:
        raise RuntimeError("Outbox events must be written inside the business transaction.")
    correlation_id = str(structlog.contextvars.get_contextvars().get("correlation_id", ""))
    return OutboxEvent.objects.create(
        tenant_id=ctx.tenant_id,
        event_type=event_type,
        event_version=version,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        correlation_id=correlation_id[:64],
    )


def envelope(event: OutboxEvent) -> dict[str, Any]:
    return {
        "id": str(event.event_id),
        "type": f"{event.event_type}.v{event.event_version}",
        "tenant": current_tenant().slug,
        "occurred_at": event.occurred_at.isoformat(),
        "correlation_id": event.correlation_id,
        "aggregate": {"type": event.aggregate_type, "id": event.aggregate_id},
        "data": event.payload,
    }


Sink = Callable[[dict[str, Any]], None]


def log_sink(message: dict[str, Any]) -> None:
    logger.info("outbox.event.delivered", event_id=message["id"], event_type=message["type"])


def relay_batch(sink: Sink = log_sink, batch_size: int = 100) -> int:
    """Deliver one batch of pending events (at-least-once, FOR UPDATE SKIP LOCKED)."""
    ctx = current_tenant()
    delivered = 0
    with transaction.atomic(using=ctx.db_alias):
        batch = list(
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(status=OutboxStatus.PENDING)
            .order_by("seq")[:batch_size]
        )
        for event in batch:
            event.attempts += 1
            try:
                sink(envelope(event))
            except (OSError, ValueError, RuntimeError) as exc:  # transport-class failures
                event.last_error = f"{type(exc).__name__}"[:300]
                if event.attempts >= MAX_ATTEMPTS:
                    event.status = OutboxStatus.DEAD
                event.save(update_fields=["attempts", "last_error", "status"])
                continue
            event.status = OutboxStatus.DISPATCHED
            event.dispatched_at = now()
            event.save(update_fields=["attempts", "status", "dispatched_at"])
            delivered += 1
    return delivered
