"""Business transactions, their append-only state history, holds, and idempotency records.

The journal (ledger) is the financial truth; this context records *why* and *in what
state* a business operation is (docs/domain/transaction-lifecycle.md).
"""

import uuid

from django.db import models
from django.db.models import F, Q

from next_core.platform.persistence import (
    AppendOnlyManager,
    AppendOnlyModel,
    TenantScopedAppendOnlyManager,
    TenantScopedManager,
)


class TxnType(models.TextChoices):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRANSFER = "TRANSFER"
    HOLD = "HOLD"
    DISBURSEMENT = "DISBURSEMENT"
    REPAYMENT = "REPAYMENT"
    REVERSAL = "REVERSAL"
    INTEREST_ACCRUAL = "INTEREST_ACCRUAL"
    INTEREST_CAPITALIZATION = "INTEREST_CAPITALIZATION"


class TxnState(models.TextChoices):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    REJECTED = "REJECTED"
    AUTHORIZED = "AUTHORIZED"
    HELD = "HELD"
    POSTED = "POSTED"
    SETTLED = "SETTLED"
    REVERSED = "REVERSED"
    VOIDED = "VOIDED"
    FAILED = "FAILED"


TERMINAL_STATES = frozenset({"REJECTED", "SETTLED", "REVERSED", "VOIDED", "FAILED"})


class BusinessTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    type = models.CharField(max_length=24, choices=TxnType.choices)
    state = models.CharField(max_length=10, choices=TxnState.choices, default="RECEIVED")
    amount_minor = models.BigIntegerField()
    currency = models.CharField(max_length=3)
    debit_account_id = models.UUIDField(null=True, blank=True, db_index=True)
    credit_account_id = models.UUIDField(null=True, blank=True, db_index=True)
    fees = models.JSONField(default=list, blank=True)
    journal_entry_ids = models.JSONField(default=list, blank=True)
    reference = models.CharField(max_length=64, blank=True, default="")
    narrative = models.CharField(max_length=200, blank=True, default="")
    channel = models.CharField(max_length=20, blank=True, default="API")
    business_date = models.DateField()
    value_date = models.DateField()
    reversal_of = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by"
    )
    product_versions = models.JSONField(default=dict, blank=True)
    rejection_code = models.CharField(max_length=40, blank=True, default="")
    rejection_detail = models.CharField(max_length=300, blank=True, default="")
    initiated_by = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager["BusinessTransaction"]()
    all_objects = models.Manager["BusinessTransaction"]()

    class Meta:
        db_table = "business_transaction"
        base_manager_name = "all_objects"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount_minor__gt=0), name="txn_amount_positive"),
            models.CheckConstraint(
                condition=~Q(state="REJECTED") | ~Q(rejection_code=""),
                name="txn_rejection_has_code",
            ),
        ]
        indexes = [models.Index(fields=["tenant_id", "created_at"], name="txn_created_idx")]


class TransactionStateTransition(AppendOnlyModel):
    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField()
    transaction = models.ForeignKey(
        BusinessTransaction, on_delete=models.PROTECT, related_name="transitions"
    )
    from_state = models.CharField(max_length=10, blank=True, default="")
    to_state = models.CharField(max_length=10)
    reason = models.CharField(max_length=300, blank=True, default="")
    actor = models.CharField(max_length=255)
    occurred_at = models.DateTimeField(auto_now_add=True)

    objects = TenantScopedAppendOnlyManager["TransactionStateTransition"]()
    all_objects = AppendOnlyManager["TransactionStateTransition"]()

    class Meta:
        db_table = "txn_state_transition"
        base_manager_name = "all_objects"
        ordering = ["id"]


class HoldStatus(models.TextChoices):
    ACTIVE = "ACTIVE"
    CAPTURED = "CAPTURED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class Hold(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    account_id = models.UUIDField(db_index=True)
    balance_id = models.UUIDField()
    transaction = models.OneToOneField(
        BusinessTransaction, on_delete=models.PROTECT, related_name="hold"
    )
    amount_minor = models.BigIntegerField()
    captured_minor = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=8, choices=HoldStatus.choices, default="ACTIVE")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager["Hold"]()
    all_objects = models.Manager["Hold"]()

    class Meta:
        db_table = "txn_hold"
        base_manager_name = "all_objects"
        constraints = [
            models.CheckConstraint(condition=Q(amount_minor__gt=0), name="hold_amount_positive"),
            models.CheckConstraint(
                condition=Q(captured_minor__gte=0, captured_minor__lte=F("amount_minor")),
                name="hold_capture_bounded",
            ),
        ]


class IdempotencyRecord(models.Model):
    """ADR-0006: scope (tenant, operation, client, key); written in the same DB transaction
    as the business effect; replays the stored response; hash mismatch → 409."""

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField()
    operation = models.CharField(max_length=60)
    client_id = models.CharField(max_length=255)
    key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=14, default="PROCESSING")
    response_status = models.PositiveSmallIntegerField(null=True)
    response_body = models.JSONField(null=True)
    transaction_id = models.UUIDField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)

    objects = TenantScopedManager["IdempotencyRecord"]()
    all_objects = models.Manager["IdempotencyRecord"]()

    class Meta:
        db_table = "idempotency_record"
        base_manager_name = "all_objects"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "operation", "client_id", "key"], name="idempotency_scope_uniq"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["PROCESSING", "COMPLETED", "FAILED_FINAL"]),
                name="idempotency_status",
            ),
        ]
