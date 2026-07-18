"""Append-only audit evidence (data plane — lives in each tenant's database).

Rows are never updated or deleted by application code; the model layer refuses updates.
Database-level grant hardening (revoking UPDATE/DELETE from the application role) ships
with the provisioning tooling (tracked as OD-20) — the same defense-in-depth pattern the
ledger will use in Phase 3.
"""

import uuid
from typing import Any

from django.db import models

from next_core.tenancy.context import current_tenant


class TenantScopedAuditManager(models.Manager["AuditEvent"]):
    """Every queryset is bound to the current tenant — both by database routing (router)
    and by an explicit tenant_id predicate (belt and braces)."""

    def get_queryset(self) -> models.QuerySet["AuditEvent"]:
        return super().get_queryset().filter(tenant_id=current_tenant().tenant_id)


class ActorType(models.TextChoices):
    USER = "USER"
    SERVICE = "SERVICE"
    SYSTEM = "SYSTEM"


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.CharField(max_length=255)
    actor_type = models.CharField(max_length=8, choices=ActorType.choices)
    operation = models.CharField(max_length=100, db_index=True)
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=255)
    correlation_id = models.CharField(max_length=64)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)

    objects = TenantScopedAuditManager()

    class Meta:
        db_table = "audit_event"
        ordering = ["-occurred_at", "-id"]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise TypeError("AuditEvent is append-only; updates are prohibited.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("AuditEvent is append-only; deletes are prohibited.")
