"""Integrity verification: reconstruct every projection from postings and compare
(invariants 9/10). Findings are persisted as evidence (IntegrityRun) and emitted as an
``integrity.mismatch`` outbox event. Postings are the truth; a mismatch means the
projection must not be trusted until investigated.
"""

from typing import Any

from django.db import transaction
from django.db.models import Count, Q, Sum

from next_core.ledger.domain import Direction, book_balance
from next_core.ledger.models import IntegrityRun, JournalEntry, LedgerBalance, Posting
from next_core.platform.outbox.service import emit
from next_core.tenancy.context import current_tenant


def _sums(qs: Any) -> Any:
    return qs.annotate(
        d=Sum("amount", filter=Q(direction="DEBIT"), default=0),
        c=Sum("amount", filter=Q(direction="CREDIT"), default=0),
    )


def verify_ledger() -> IntegrityRun:
    ctx = current_tenant()
    findings: list[dict[str, Any]] = []

    rebuilt = {
        row["balance_id"]: (row["d"], row["c"])
        for row in _sums(Posting.objects.values("balance_id"))
    }
    balances = list(LedgerBalance.objects.all())
    for b in balances:
        d, c = rebuilt.get(b.id, (0, 0))
        expected_book = book_balance(Direction(b.normal_side), d, c)
        if (b.debit_total, b.credit_total, b.book_balance) != (d, c, expected_book):
            findings.append(
                {
                    "kind": "PROJECTION_MISMATCH",
                    "balance_id": str(b.id),
                    "projection": [b.debit_total, b.credit_total, b.book_balance],
                    "reconstructed": [d, c, expected_book],
                }
            )

    unbalanced = _sums(Posting.objects.values("entry_id", "currency")).filter(~Q(d=0) | ~Q(c=0))
    for row in unbalanced:
        if row["d"] != row["c"]:
            findings.append(
                {
                    "kind": "UNBALANCED_ENTRY",
                    "entry_id": str(row["entry_id"]),
                    "currency": row["currency"],
                }
            )
    thin = JournalEntry.objects.annotate(n=Count("postings")).filter(n__lt=2)
    for e in thin:
        findings.append({"kind": "ENTRY_WITHOUT_POSTINGS", "entry_id": str(e.id)})

    for row in _sums(Posting.objects.values("currency")):
        if row["d"] != row["c"]:
            findings.append({"kind": "TRIAL_BALANCE_BROKEN", "currency": row["currency"]})

    with transaction.atomic(using=ctx.db_alias):
        run = IntegrityRun.objects.create(
            tenant_id=ctx.tenant_id,
            balances_checked=len(balances),
            entries_checked=JournalEntry.objects.count(),
            ok=not findings,
            findings=findings[:1000],
        )
        if findings:
            emit(
                "integrity.mismatch",
                aggregate_type="integrity_run",
                aggregate_id=str(run.id),
                payload={"run_id": str(run.id), "finding_count": len(findings)},
            )
    return run


def trial_balance() -> list[dict[str, Any]]:
    """Per GL account and currency: debit total, credit total, net per normal side."""
    rows = (
        LedgerBalance.objects.values(
            "gl_account__code", "gl_account__name", "gl_account__type", "normal_side", "currency"
        )
        .annotate(d=Sum("debit_total"), c=Sum("credit_total"))
        .order_by("gl_account__code", "currency")
    )
    out = []
    for r in rows:
        out.append(
            {
                "gl_code": r["gl_account__code"],
                "gl_name": r["gl_account__name"],
                "gl_type": r["gl_account__type"],
                "currency": r["currency"],
                "debit_total": r["d"] or 0,
                "credit_total": r["c"] or 0,
                "net": book_balance(Direction(r["normal_side"]), r["d"] or 0, r["c"] or 0),
            }
        )
    return out
