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
    """Deliver one batch of pending events: at-least-once, ordered per aggregate (a failed
    event holds back later events of the same aggregate), one relay per tenant."""
    ctx = current_tenant()
    delivered = 0
    with transaction.atomic(using=ctx.db_alias):
        # One relay per tenant database at a time: per-aggregate order cannot be overtaken
        # by a concurrent relay (transaction-scoped advisory lock; coordination only).
        with connections[ctx.db_alias].cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock(hashtext('next_core.outbox_relay'))")
            if not cur.fetchone()[0]:
                return 0
        batch = list(
            OutboxEvent.objects.select_for_update()
            .filter(status=OutboxStatus.PENDING)
            .order_by("seq")[:batch_size]
        )
        blocked: set[tuple[str, str]] = set()
        for event in batch:
            aggregate = (event.aggregate_type, event.aggregate_id)
            if aggregate in blocked:
                continue  # an earlier event of this aggregate failed: keep per-aggregate order
            event.attempts += 1
            try:
                sink(envelope(event))
            except (OSError, ValueError, RuntimeError) as exc:  # transport-class failures
                event.last_error = f"{type(exc).__name__}"[:300]
                if event.attempts >= MAX_ATTEMPTS:
                    event.status = OutboxStatus.DEAD
                event.save(update_fields=["attempts", "last_error", "status"])
                blocked.add(aggregate)
                continue
            event.status = OutboxStatus.DISPATCHED
            event.dispatched_at = now()
            event.save(update_fields=["attempts", "status", "dispatched_at"])
            delivered += 1
    return delivered
