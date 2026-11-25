"""Customer accounts (data plane): the contract, not the value. Value lives in ledger
balances referenced by id. Accounts are never deleted (invariant 20): closure is a state;
status history is append-only."""

import uuid

from django.db import models
from django.db.models import Q

from next_core.platform.persistence import (
    AppendOnlyManager,
    AppendOnlyModel,
    TenantScopedAppendOnlyManager,
    TenantScopedManager,
)


class AccountStatus(models.TextChoices):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    DORMANT = "DORMANT"
    CLOSED = "CLOSED"


class Account(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    number = models.CharField(max_length=20)
    party_id = models.UUIDField(db_index=True)
    product_id = models.UUIDField()
    product_version_id = models.UUIDField()
    product_code = models.CharField(max_length=40)
    category = models.CharField(max_length=20)
    balance_side = models.CharField(max_length=10)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=8, choices=AccountStatus.choices, default="ACTIVE")
    debit_blocked = models.BooleanField(default=False)
    credit_blocked = models.BooleanField(default=False)
    parameter_overrides = models.JSONField(default=dict, blank=True)
    principal_balance_id = models.UUIDField(unique=True)
    interest_balance_id = models.UUIDField(null=True, blank=True, unique=True)
    nickname = models.CharField(max_length=80, blank=True, default="")
    opened_on = models.DateField()
    maturity_date = models.DateField(null=True, blank=True)
    closed_on = models.DateField(null=True, blank=True)
    last_activity_on = models.DateField(null=True, blank=True)
    interest_accrued_through = models.DateField(null=True, blank=True)
    version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager["Account"]()
    all_objects = models.Manager["Account"]()

    class Meta:
        db_table = "account"
        base_manager_name = "all_objects"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "number"], name="account_number_uniq"),
            models.CheckConstraint(
                condition=Q(status="CLOSED", closed_on__isnull=False)
                | (~Q(status="CLOSED") & Q(closed_on__isnull=True)),
                name="account_closed_on_shape",
            ),
            models.CheckConstraint(
                condition=Q(currency__regex=r"^[A-Z]{3}$"), name="account_currency"
            ),
        ]


class AccountStatusChange(AppendOnlyModel):
    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="status_history")
    from_status = models.CharField(max_length=8, blank=True, default="")
    to_status = models.CharField(max_length=8)
    debit_blocked = models.BooleanField()
    credit_blocked = models.BooleanField()
    reason = models.CharField(max_length=300, blank=True, default="")
    actor = models.CharField(max_length=255)
    occurred_at = models.DateTimeField(auto_now_add=True)

    objects = TenantScopedAppendOnlyManager["AccountStatusChange"]()
    all_objects = AppendOnlyManager["AccountStatusChange"]()

    class Meta:
        db_table = "account_status_change"
        base_manager_name = "all_objects"
