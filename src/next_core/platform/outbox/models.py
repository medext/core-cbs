"""Transactional outbox (ADR-0007) — one table per tenant database.

Rows are inserted in the same DB transaction as the state change they announce; the relay
publishes them after commit (invariant 25). ``seq`` gives a stable per-database order, so
delivery is ordered per aggregate.
"""

import uuid

from django.db import models

from next_core.platform.persistence import TenantScopedManager


class OutboxStatus(models.TextChoices):
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    DEAD = "DEAD"


class OutboxEvent(models.Model):
    seq = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    event_type = models.CharField(max_length=100)
    event_version = models.PositiveSmallIntegerField(default=1)
    aggregate_type = models.CharField(max_length=60)
    aggregate_id = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    correlation_id = models.CharField(max_length=64, blank=True, default="")
    occurred_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=10, choices=OutboxStatus.choices, default=OutboxStatus.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True, default="")

    objects = TenantScopedManager["OutboxEvent"]()
    all_objects = models.Manager["OutboxEvent"]()

    class Meta:
        db_table = "outbox_event"
        base_manager_name = "all_objects"
        indexes = [models.Index(fields=["status", "seq"], name="outbox_pending_idx")]
