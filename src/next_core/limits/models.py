"""Limit consumption counters (data plane).

One row per (account, limit code, currency, window key). Rows are created with
INSERT … ON CONFLICT DO NOTHING and consumed under SELECT … FOR UPDATE inside the business
transaction — funds check, limit consumption and posting form one atomic decision.
"""

from django.db import models
from django.db.models import Q

from next_core.platform.persistence import TenantScopedManager


class LimitCounter(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField()
    account_id = models.UUIDField()
    limit_code = models.CharField(max_length=40)
    currency = models.CharField(max_length=3)
    window_key = models.CharField(max_length=12)  # D2026-11-25 | M2026-11
    consumed_amount = models.BigIntegerField(default=0)
    consumed_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager["LimitCounter"]()
    all_objects = models.Manager["LimitCounter"]()

    class Meta:
        db_table = "limit_counter"
        base_manager_name = "all_objects"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "account_id", "limit_code", "currency", "window_key"],
                name="limit_counter_uniq",
            ),
            models.CheckConstraint(condition=Q(consumed_amount__gte=0), name="limit_amount_nonneg"),
        ]
