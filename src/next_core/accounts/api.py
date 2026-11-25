"""Accounts API — /api/v1/accounts."""

from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from next_core.accounts import application as svc
from next_core.accounts.models import Account, AccountStatus, AccountStatusChange
from next_core.iam.permissions import ACCOUNTS_CONTROL, ACCOUNTS_OPEN, ACCOUNTS_READ
from next_core.iam.views import DataPlaneView
from next_core.ledger import application as ledger
from next_core.limits.application import current_usage
from next_core.platform import clock
from next_core.platform.api import (
    OBJ,
    OBJ_LIST,
    BoundedCursorPagination,
    StrictSerializer,
    actor_from,
)
from next_core.platform.errors import ValidationFailedError
from next_core.platform.money import CURRENCIES, Money

TAG = ["Accounts"]


class OpenAccountSerializer(StrictSerializer):
    party_id = serializers.UUIDField()
    product_id = serializers.UUIDField()
    currency = serializers.ChoiceField(choices=sorted(CURRENCIES))
    parameter_overrides = serializers.JSONField(required=False, default=dict)
    nickname = serializers.CharField(max_length=80, required=False, default="")


class StatusSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=AccountStatus.choices)
    reason = serializers.CharField(max_length=300)


class BlocksSerializer(StrictSerializer):
    debit_blocked = serializers.BooleanField()
    credit_blocked = serializers.BooleanField()
    reason = serializers.CharField(max_length=300)


def balance_dict(b: ledger.BalanceView) -> dict[str, Any]:
    """Full qualified balance set — never a bare 'balance' (balance-semantics.md)."""

    def w(minor: int) -> str:
        return Money(minor, b.currency).to_wire()

    return {
        "balance_id": str(b.id),
        "purpose": b.purpose,
        "currency": b.currency,
        "gl_code": b.gl_code,
        "book_balance": w(b.book_balance),
        "available_balance": w(b.available_balance),
        "cleared_balance": w(b.book_balance),  # MVP: same-day value dating (spec)
        "held_amount": w(b.held_amount),
        "pending_debit": w(b.pending_debit),
        "pending_credit": w(b.pending_credit),
        "overdraft_limit": w(b.overdraft_limit),
        "as_of": {
            "business_date": clock.business_date().isoformat(),
            "entry_seq": b.last_entry_seq,
        },
    }


class AccountSerializer(serializers.ModelSerializer[Account]):
    class Meta:
        model = Account
        fields = (
            "id",
            "number",
            "party_id",
            "product_id",
            "product_code",
            "product_version_id",
            "category",
            "balance_side",
            "currency",
            "status",
            "debit_blocked",
            "credit_blocked",
            "parameter_overrides",
            "nickname",
            "opened_on",
            "maturity_date",
            "closed_on",
            "last_activity_on",
            "version",
            "created_at",
        )
        read_only_fields = fields


class AccountDetailSerializer(AccountSerializer):
    balances = serializers.SerializerMethodField()

    class Meta(AccountSerializer.Meta):
        fields = (*AccountSerializer.Meta.fields, "balances")  # type: ignore[assignment]
        read_only_fields = fields  # type: ignore[assignment]

    def get_balances(self, obj: Account) -> list[dict[str, Any]]:
        return [balance_dict(b) for b in ledger.balances_for_owner(obj.id)]


class AccountListView(DataPlaneView):
    method_permissions = {"GET": ACCOUNTS_READ, "POST": ACCOUNTS_OPEN}
    FILTERS = ("party_id", "status", "product_code", "currency", "number")

    @extend_schema(
        tags=TAG,
        summary="List accounts",
        parameters=[OpenApiParameter(f, str, required=False) for f in FILTERS],
        responses=AccountSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        qs = Account.objects.all()
        for name in self.FILTERS:
            value = request.query_params.get(name)
            if value:
                if name == "party_id":
                    try:
                        UUID(value)
                    except ValueError as exc:
                        raise ValidationFailedError("party_id must be a UUID.") from exc
                qs = qs.filter(**{name: value[:64]})
        paginator = BoundedCursorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(AccountSerializer(page, many=True).data)

    @extend_schema(
        tags=TAG,
        summary="Open an account on the product's ACTIVE version",
        request=OpenAccountSerializer,
        responses={201: AccountDetailSerializer},
    )
    def post(self, request: Request) -> Response:
        ser = OpenAccountSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        account = svc.open_account(
            party_id=v["party_id"],
            product_id=v["product_id"],
            currency=v["currency"],
            parameter_overrides=v["parameter_overrides"],
            nickname=v["nickname"],
            actor=actor_from(request),
        )
        return Response(AccountDetailSerializer(account).data, status=201)


class AccountDetailView(DataPlaneView):
    method_permissions = {"GET": ACCOUNTS_READ}

    @extend_schema(
        tags=TAG, summary="Get an account with its balances", responses=AccountDetailSerializer
    )
    def get(self, request: Request, account_id: UUID) -> Response:
        return Response(AccountDetailSerializer(svc.get_account(account_id)).data)


class AccountBalancesView(DataPlaneView):
    method_permissions = {"GET": ACCOUNTS_READ}

    @extend_schema(
        tags=TAG,
        summary="Qualified balances (book/available/held/…)",
        responses={200: OBJ_LIST},
    )
    def get(self, request: Request, account_id: UUID) -> Response:
        account = svc.get_account(account_id)
        return Response([balance_dict(b) for b in ledger.balances_for_owner(account.id)])


class AccountStatementView(DataPlaneView):
    method_permissions = {"GET": ACCOUNTS_READ}

    @extend_schema(
        tags=TAG,
        summary="Statement: postings with running book balance (cursor = posting id)",
        parameters=[
            OpenApiParameter(
                "purpose",
                str,
                required=False,
                description="PRINCIPAL (default) or ACCRUED_INTEREST",
            ),
            OpenApiParameter("after", int, required=False),
            OpenApiParameter("limit", int, required=False),
        ],
        responses={200: OBJ},
    )
    def get(self, request: Request, account_id: UUID) -> Response:
        account = svc.get_account(account_id)
        purpose = request.query_params.get("purpose", "PRINCIPAL")
        balance_id = (
            account.principal_balance_id if purpose == "PRINCIPAL" else account.interest_balance_id
        )
        if purpose not in ("PRINCIPAL", "ACCRUED_INTEREST") or balance_id is None:
            raise ValidationFailedError("Unknown balance purpose for this account.")
        try:
            after = int(request.query_params.get("after", "0"))
            limit = min(max(int(request.query_params.get("limit", "50")), 1), 200)
        except ValueError as exc:
            raise ValidationFailedError("after/limit must be integers.") from exc
        lines, has_more = ledger.statement(balance_id, after_posting_id=after, limit=limit)
        cur = account.currency

        def w(minor: int) -> str:
            return Money(minor, cur).to_wire()

        return Response(
            {
                "account_id": str(account.id),
                "purpose": purpose,
                "currency": cur,
                "lines": [
                    {
                        "posting_id": ln.posting_id,
                        "entry_id": str(ln.entry_id),
                        "entry_seq": ln.entry_seq,
                        "business_date": ln.business_date.isoformat(),
                        "value_date": ln.value_date.isoformat(),
                        "posted_at": ln.posted_at.isoformat(),
                        "direction": ln.direction,
                        "amount": w(ln.amount_minor),
                        "description": ln.description,
                        "source": {"type": ln.source_type, "id": str(ln.source_id)},
                        "running_book_balance": w(ln.running_book_balance),
                    }
                    for ln in lines
                ],
                "next_after": lines[-1].posting_id if has_more and lines else None,
            }
        )


class AccountLimitsView(DataPlaneView):
    method_permissions = {"GET": ACCOUNTS_READ}

    @extend_schema(
        tags=TAG,
        summary="Current limit usage (windowed limits)",
        responses={200: OBJ_LIST},
    )
    def get(self, request: Request, account_id: UUID) -> Response:
        account = svc.get_account(account_id)
        snap = svc.snapshot(account)
        usage = current_usage(
            account.id, snap.definition.limits, account.currency, clock.business_date()
        )
        return Response(
            [
                {
                    "code": u.code,
                    "window": u.window,
                    "max_amount": u.max_amount.to_wire() if u.max_amount else None,
                    "consumed_amount": u.consumed_amount.to_wire(),
                    "remaining_amount": u.remaining_amount.to_wire()
                    if u.remaining_amount
                    else None,
                    "max_count": u.max_count,
                    "consumed_count": u.consumed_count,
                }
                for u in usage
            ]
        )


class AccountStatusView(DataPlaneView):
    method_permissions = {"POST": ACCOUNTS_CONTROL}

    @extend_schema(
        tags=TAG,
        summary="Change status (ACTIVE/FROZEN/DORMANT/CLOSED)",
        request=StatusSerializer,
        responses=AccountSerializer,
    )
    def post(self, request: Request, account_id: UUID) -> Response:
        ser = StatusSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        account = svc.change_status(
            account_id,
            ser.validated_data["status"],
            ser.validated_data["reason"],
            actor_from(request),
        )
        return Response(AccountSerializer(account).data)


class AccountBlocksView(DataPlaneView):
    method_permissions = {"POST": ACCOUNTS_CONTROL}

    @extend_schema(
        tags=TAG,
        summary="Set debit/credit blocks",
        request=BlocksSerializer,
        responses=AccountSerializer,
    )
    def post(self, request: Request, account_id: UUID) -> Response:
        ser = BlocksSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        account = svc.set_blocks(
            account_id,
            debit=v["debit_blocked"],
            credit=v["credit_blocked"],
            reason=v["reason"],
            actor=actor_from(request),
        )
        return Response(AccountSerializer(account).data)


class AccountHistoryView(DataPlaneView):
    method_permissions = {"GET": ACCOUNTS_READ}

    @extend_schema(
        tags=TAG,
        summary="Status & block history (append-only)",
        responses={200: OBJ_LIST},
    )
    def get(self, request: Request, account_id: UUID) -> Response:
        svc.get_account(account_id)
        rows = AccountStatusChange.objects.filter(account_id=account_id).order_by("id")
        return Response(
            [
                {
                    "from": r.from_status or None,
                    "to": r.to_status,
                    "debit_blocked": r.debit_blocked,
                    "credit_blocked": r.credit_blocked,
                    "reason": r.reason,
                    "actor": r.actor,
                    "occurred_at": r.occurred_at.isoformat(),
                }
                for r in rows
            ]
        )
