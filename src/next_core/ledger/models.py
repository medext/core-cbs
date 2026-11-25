"""Ledger persistence (data plane — each tenant's database).

Constraint inventory (docs/accounting/ledger-architecture.md):
- CHECKs declared here (amount > 0, direction, currency shape, projection consistency).
- Triggers installed by migration 0002 (the database authority):
  * ``ledger_append_only``           — UPDATE/DELETE on journal entries & postings refused;
  * ``ledger_entry_balanced``        — DEFERRED constraint trigger: per (entry, currency)
                                       Σdebit = Σcredit and ≥ 2 postings, checked at COMMIT;
  * ``ledger_posting_currency``      — posting currency must equal its balance's currency;
  * ``ledger_balance_guard``         — balance rows: immutable identity columns, monotonic
                                       totals, version += 1 on every write, no DELETE, and
                                       the available-funds floor (invariant 18 backstop).
- No ON DELETE CASCADE anywhere (PROTECT everywhere).
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

DIRECTIONS = (("DEBIT", "DEBIT"), ("CREDIT", "CREDIT"))
CURRENCY_RE = r"^[A-Z]{3}$"


class GLAccount(models.Model):
    """Chart-of-accounts entry. Retired, never deleted, once referenced."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=120)
    type = models.CharField(
        max_length=10,
        choices=[(t, t) for t in ("ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE")],
    )
    normal_side = models.CharField(max_length=6, choices=DIRECTIONS)
    parent_code = models.CharField(max_length=20, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantScopedManager["GLAccount"]()
    all_objects = models.Manager["GLAccount"]()

    class Meta:
        db_table = "ledger_gl_account"
        base_manager_name = "all_objects"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "code"], name="ledger_gl_code_uniq"),
            models.CheckConstraint(
                condition=(
                    Q(type__in=["ASSET", "EXPENSE"], normal_side="DEBIT")
                    | Q(type__in=["LIABILITY", "EQUITY", "INCOME"], normal_side="CREDIT")
                ),
                name="ledger_gl_normal_side_by_type",
            ),
        ]


class LedgerBalance(models.Model):
    """The store of value. Projection fields are written ONLY by the posting service."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    gl_account = models.ForeignKey(GLAccount, on_delete=models.PROTECT, related_name="+")
    currency = models.CharField(max_length=3)
    normal_side = models.CharField(max_length=6, choices=DIRECTIONS)
    owner_type = models.CharField(
        max_length=10, choices=[("ACCOUNT", "ACCOUNT"), ("INTERNAL", "INTERNAL")]
    )
    owner_id = models.UUIDField(null=True, blank=True)
    purpose = models.CharField(max_length=30, default="PRINCIPAL")
    debit_total = models.BigIntegerField(default=0)
    credit_total = models.BigIntegerField(default=0)
    book_balance = models.BigIntegerField(default=0)
    held_amount = models.BigIntegerField(default=0)
    pending_debit = models.BigIntegerField(default=0)
    pending_credit = models.BigIntegerField(default=0)
    overdraft_limit = models.BigIntegerField(default=0)
    funds_enforced = models.BooleanField(default=False)
    version = models.BigIntegerField(default=0)
    last_entry_seq = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager["LedgerBalance"]()
    all_objects = models.Manager["LedgerBalance"]()

    class Meta:
        db_table = "ledger_balance"
        base_manager_name = "all_objects"
        constraints = [
            models.CheckConstraint(condition=Q(currency__regex=CURRENCY_RE), name="lb_currency"),
            models.CheckConstraint(
                condition=Q(debit_total__gte=0, credit_total__gte=0), name="lb_totals_nonneg"
            ),
            models.CheckConstraint(
                condition=Q(held_amount__gte=0, pending_debit__gte=0, pending_credit__gte=0),
                name="lb_reservations_nonneg",
            ),
            models.CheckConstraint(condition=Q(overdraft_limit__gte=0), name="lb_overdraft_nonneg"),
            models.CheckConstraint(
                condition=(
                    Q(normal_side="CREDIT", book_balance=F("credit_total") - F("debit_total"))
                    | Q(normal_side="DEBIT", book_balance=F("debit_total") - F("credit_total"))
                ),
                name="lb_book_consistent",
            ),
            models.CheckConstraint(
                condition=(
                    Q(owner_type="ACCOUNT", owner_id__isnull=False)
                    | Q(owner_type="INTERNAL", owner_id__isnull=True)
                ),
                name="lb_owner_shape",
            ),
            models.UniqueConstraint(
                fields=["tenant_id", "owner_id", "purpose", "currency"],
                condition=Q(owner_type="ACCOUNT"),
                name="lb_account_dimension_uniq",
            ),
            models.UniqueConstraint(
                fields=["tenant_id", "gl_account", "currency", "purpose"],
                condition=Q(owner_type="INTERNAL"),
                name="lb_internal_uniq",
            ),
        ]


class JournalEntry(AppendOnlyModel):
    """Immutable. ``seq`` is the canonical accounting order within the tenant database."""

    seq = models.BigAutoField(primary_key=True)
    id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    source_type = models.CharField(max_length=40)
    source_id = models.UUIDField()
    purpose = models.CharField(max_length=40)
    business_date = models.DateField()
    value_date = models.DateField()
    posted_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=200, blank=True, default="")
    reversal_of = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reversed_by",
        to_field="id",
    )
    metadata = models.JSONField(default=dict, blank=True)

    objects = TenantScopedAppendOnlyManager["JournalEntry"]()
    all_objects = AppendOnlyManager["JournalEntry"]()

    class Meta:
        db_table = "ledger_journal_entry"
        base_manager_name = "all_objects"
        constraints = [
            # Ledger-level at-most-once backstop: one entry per (source, purpose).
            models.UniqueConstraint(
                fields=["tenant_id", "source_type", "source_id", "purpose"],
                name="je_source_purpose_uniq",
            ),
        ]


class Posting(AppendOnlyModel):
    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField()
    entry = models.ForeignKey(
        JournalEntry, on_delete=models.PROTECT, related_name="postings", to_field="id"
    )
    balance = models.ForeignKey(LedgerBalance, on_delete=models.PROTECT, related_name="+")
    line_no = models.PositiveSmallIntegerField()
    direction = models.CharField(max_length=6, choices=DIRECTIONS)
    amount = models.BigIntegerField()
    currency = models.CharField(max_length=3)

    objects = TenantScopedAppendOnlyManager["Posting"]()
    all_objects = AppendOnlyManager["Posting"]()

    class Meta:
        db_table = "ledger_posting"
        base_manager_name = "all_objects"
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="posting_amount_positive"),
            models.CheckConstraint(
                condition=Q(direction__in=["DEBIT", "CREDIT"]), name="posting_direction"
            ),
            models.CheckConstraint(
                condition=Q(currency__regex=CURRENCY_RE), name="posting_currency"
            ),
            models.UniqueConstraint(fields=["entry", "line_no"], name="posting_line_uniq"),
        ]
        indexes = [models.Index(fields=["balance", "id"], name="posting_balance_idx")]


class IntegrityRun(AppendOnlyModel):
    """Persisted evidence of a reconstruction / integrity verification run."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField()
    started_at = models.DateTimeField(auto_now_add=True)
    balances_checked = models.PositiveIntegerField()
    entries_checked = models.PositiveIntegerField()
    ok = models.BooleanField()
    findings = models.JSONField(default=list)

    objects = TenantScopedAppendOnlyManager["IntegrityRun"]()
    all_objects = AppendOnlyManager["IntegrityRun"]()

    class Meta:
        db_table = "ledger_integrity_run"
        base_manager_name = "all_objects"
