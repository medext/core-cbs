"""Ledger read API (no write endpoint exists — balances change only through business
transactions) + operations endpoints (integrity verification, EoD steps)."""

from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from next_core.iam.permissions import LEDGER_READ, OPERATIONS_RUN
from next_core.iam.views import DataPlaneView
from next_core.ledger.application import entry_lines, list_gl_accounts
from next_core.ledger.integrity import trial_balance, verify_ledger
from next_core.ledger.models import JournalEntry
from next_core.platform import clock
from next_core.platform.api import OBJ, OBJ_LIST
from next_core.platform.errors import NotFoundError
from next_core.platform.money import Money

TAG = ["Ledger"]
OPS_TAG = ["Operations"]


class GLAccountsView(DataPlaneView):
    method_permissions = {"GET": LEDGER_READ}

    @extend_schema(tags=TAG, summary="Chart of accounts", responses={200: OBJ_LIST})
    def get(self, request: Request) -> Response:
        return Response(
            [
                {
                    "code": g.code,
                    "name": g.name,
                    "type": g.type,
                    "normal_side": g.normal_side,
                    "parent_code": g.parent_code or None,
                    "is_active": g.is_active,
                }
                for g in list_gl_accounts()
            ]
        )


class TrialBalanceView(DataPlaneView):
    method_permissions = {"GET": LEDGER_READ}

    @extend_schema(
        tags=TAG,
        summary="Trial balance per GL account and currency",
        responses={200: OBJ},
    )
    def get(self, request: Request) -> Response:
        rows = trial_balance()
        totals: dict[str, dict[str, int]] = {}
        for r in rows:
            t = totals.setdefault(r["currency"], {"debit": 0, "credit": 0})
            t["debit"] += r["debit_total"]
            t["credit"] += r["credit_total"]

        def w(minor: int, cur: str) -> str:
            return Money(minor, cur).to_wire()

        return Response(
            {
                "as_of": clock.now().isoformat(),
                "lines": [
                    {
                        **{k: r[k] for k in ("gl_code", "gl_name", "gl_type", "currency")},
                        "debit_total": w(r["debit_total"], r["currency"]),
                        "credit_total": w(r["credit_total"], r["currency"]),
                        "net": w(r["net"], r["currency"]),
                    }
                    for r in rows
                ],
                "totals": {
                    cur: {
                        "debit_total": w(t["debit"], cur),
                        "credit_total": w(t["credit"], cur),
                        "balanced": t["debit"] == t["credit"],
                    }
                    for cur, t in sorted(totals.items())
                },
            }
        )


class EntryDetailView(DataPlaneView):
    method_permissions = {"GET": LEDGER_READ}

    @extend_schema(tags=TAG, summary="Journal entry with postings", responses={200: OBJ})
    def get(self, request: Request, entry_id: UUID) -> Response:
        entry = JournalEntry.objects.filter(id=entry_id).first()
        if entry is None:
            raise NotFoundError("Journal entry not found.")
        reversed_by = (
            JournalEntry.objects.filter(reversal_of__id=entry.id)
            .values_list("id", flat=True)
            .first()
        )
        return Response(
            {
                "id": str(entry.id),
                "seq": entry.seq,
                "purpose": entry.purpose,
                "source": {"type": entry.source_type, "id": str(entry.source_id)},
                "business_date": entry.business_date.isoformat(),
                "value_date": entry.value_date.isoformat(),
                "posted_at": entry.posted_at.isoformat(),
                "description": entry.description,
                "reversal_of": str(entry.reversal_of_id) if entry.reversal_of_id else None,
                "reversed_by": str(reversed_by) if reversed_by else None,
                "postings": [
                    {
                        "balance_id": str(line.balance_id),
                        "direction": line.direction.value,
                        "amount": line.money.to_wire(),
                        "currency": line.money.currency,
                    }
                    for line in entry_lines(entry)
                ],
            }
        )


class IntegrityRunView(DataPlaneView):
    method_permissions = {"POST": OPERATIONS_RUN}

    @extend_schema(
        tags=OPS_TAG,
        summary="Reconstruct balances from postings and verify",
        request=None,
        responses={201: OBJ},
    )
    def post(self, request: Request) -> Response:
        run = verify_ledger()
        return Response(
            {
                "id": str(run.id),
                "ok": run.ok,
                "balances_checked": run.balances_checked,
                "entries_checked": run.entries_checked,
                "findings": run.findings,
                "started_at": run.started_at.isoformat(),
            },
            status=201,
        )
