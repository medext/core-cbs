"""Transactions API — deposits, withdrawals, transfers, loans, holds, reversals, simulation.

Every financial write requires ``Idempotency-Key`` (ADR-0006): replay returns the original
status + body with ``Idempotent-Replayed: true``; same key + different payload → 409
``IDEMPOTENCY_CONFLICT``. Business rejections are recorded (REJECTED transaction) and
replayed identically."""

from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from next_core.accounts.application import get_account
from next_core.iam.permissions import (
    HOLDS_MANAGE,
    LOANS_DISBURSE,
    OPERATIONS_RUN,
    TRANSACTIONS_POST,
    TRANSACTIONS_READ,
    TRANSACTIONS_REVERSE,
)
from next_core.iam.views import DataPlaneView
from next_core.platform import clock
from next_core.platform.api import (
    IDEMPOTENCY_HEADER,
    OBJ,
    OBJ_LIST,
    PROBLEM,
    BoundedCursorPagination,
    MoneyInputSerializer,
    StrictSerializer,
    actor_from,
    idempotency_key,
    outcome_response,
)
from next_core.platform.money import CURRENCIES, Money
from next_core.transactions import application as svc
from next_core.transactions.models import BusinessTransaction, Hold, TxnState, TxnType

TAG = ["Transactions"]
HOLD_TAG = ["Holds"]
LOAN_TAG = ["Loans"]
IDEM_PARAM = OpenApiParameter(
    IDEMPOTENCY_HEADER,
    str,
    OpenApiParameter.HEADER,
    required=True,
    description="Client-generated key; always retry with the same key.",
)


class _Common(StrictSerializer):
    amount = serializers.CharField(max_length=24, help_text='Decimal string, e.g. "150.00".')
    currency = serializers.ChoiceField(choices=sorted(CURRENCIES))
    reference = serializers.CharField(max_length=64, required=False, default="")
    narrative = serializers.CharField(max_length=200, required=False, default="")
    channel = serializers.RegexField(r"^[A-Z_]{2,20}$", required=False, default="API")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        money = MoneyInputSerializer(
            data={"amount": attrs["amount"], "currency": attrs["currency"]}
        )
        money.is_valid(raise_exception=True)
        attrs["money"] = money.validated_data["money"]
        return attrs


class AccountOpSerializer(_Common):
    account_id = serializers.UUIDField()


class TransferSerializer(_Common):
    source_account_id = serializers.UUIDField()
    target_account_id = serializers.UUIDField()


class DisbursementSerializer(_Common):
    target_account_id = serializers.UUIDField()


class RepaymentSerializer(_Common):
    source_account_id = serializers.UUIDField()


class HoldSerializer(_Common):
    account_id = serializers.UUIDField()
    expires_in_seconds = serializers.IntegerField(
        min_value=60, max_value=svc.MAX_HOLD_SECONDS, default=604800
    )


class CaptureSerializer(StrictSerializer):
    target_account_id = serializers.UUIDField()
    amount = serializers.CharField(max_length=24, required=False)
    currency = serializers.ChoiceField(choices=sorted(CURRENCIES), required=False)


class ReversalSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=200)


class SimulateSerializer(_Common):
    type = serializers.ChoiceField(
        choices=["DEPOSIT", "WITHDRAWAL", "TRANSFER", "DISBURSEMENT", "REPAYMENT", "HOLD"]
    )
    account_id = serializers.UUIDField(required=False)
    source_account_id = serializers.UUIDField(required=False)
    target_account_id = serializers.UUIDField(required=False)
    expires_in_seconds = serializers.IntegerField(
        min_value=60, max_value=svc.MAX_HOLD_SECONDS, default=3600
    )


class TransactionOutSerializer(serializers.Serializer[Any]):
    """Documentation shape of a business transaction (see transactions.application.to_dict)."""

    id = serializers.UUIDField()
    type = serializers.ChoiceField(choices=TxnType.choices)
    state = serializers.ChoiceField(choices=TxnState.choices)
    is_terminal = serializers.BooleanField()
    funds_reserved = serializers.BooleanField()
    amount = serializers.CharField()
    currency = serializers.CharField()
    debit_account_id = serializers.UUIDField(allow_null=True)
    credit_account_id = serializers.UUIDField(allow_null=True)
    fees = serializers.ListField(child=serializers.DictField())
    total_fees = serializers.CharField()
    reference = serializers.CharField()
    narrative = serializers.CharField()
    channel = serializers.CharField()
    business_date = serializers.DateField()
    value_date = serializers.DateField()
    journal_entry_ids = serializers.ListField(child=serializers.UUIDField())
    product_versions = serializers.DictField()
    reversal_of = serializers.UUIDField(allow_null=True)
    reversed_by = serializers.UUIDField(allow_null=True)
    rejection = serializers.DictField(allow_null=True)
    hold = serializers.DictField(allow_null=True)
    created_at = serializers.DateTimeField()


def _common(v: dict[str, Any]) -> svc.CommonFields:
    return svc.CommonFields(
        reference=v["reference"], narrative=v["narrative"], channel=v["channel"]
    )


def _payload(v: dict[str, Any], *extra: str) -> dict[str, Any]:
    money: Money = v["money"]
    body = {
        "amount": money.to_wire(),
        "currency": money.currency,
        "reference": v["reference"],
        "narrative": v["narrative"],
        "channel": v["channel"],
    }
    for name in extra:
        body[name] = str(v[name])
    return body


def _write(
    request: Request,
    operation: str,
    payload: dict[str, Any],
    work: svc.Work,
    on_reject: svc.OnReject,
) -> Response:
    key = idempotency_key(request)
    actor = actor_from(request)
    out = svc.execute_idempotent(
        svc.Idempotency(operation, actor.id, key), payload, work, on_reject
    )
    return outcome_response(out.status, out.body, out.replayed)


def _no_new_txn(_: Any) -> None:
    return None


def _schema(
    summary: str, request: Any, tags: list[str], example: dict[str, Any] | None = None
) -> Callable[[Any], Any]:
    return extend_schema(
        tags=tags,
        summary=summary,
        request=request,
        parameters=[IDEM_PARAM],
        responses={
            201: TransactionOutSerializer,
            400: PROBLEM,
            409: PROBLEM,
            422: PROBLEM,
        },
        examples=[OpenApiExample("Request", value=example, request_only=True)] if example else None,
    )


class DepositView(DataPlaneView):
    method_permissions = {"POST": TRANSACTIONS_POST}

    @_schema(
        "Cash deposit",
        AccountOpSerializer,
        TAG,
        {"account_id": "…", "amount": "1000.00", "currency": "MRU", "channel": "BRANCH"},
    )
    def post(self, request: Request) -> Response:
        ser = AccountOpSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v, actor = ser.validated_data, actor_from(request)
        return _write(
            request,
            "deposit",
            _payload(v, "account_id"),
            lambda: svc.deposit(v["account_id"], v["money"], _common(v), actor),
            svc.rejecter(
                type=TxnType.DEPOSIT,
                amount=v["money"],
                actor=actor,
                credit_account_id=v["account_id"],
                reference=v["reference"],
                narrative=v["narrative"],
                channel=v["channel"],
            ),
        )


class WithdrawalView(DataPlaneView):
    method_permissions = {"POST": TRANSACTIONS_POST}

    @_schema("Cash withdrawal", AccountOpSerializer, TAG)
    def post(self, request: Request) -> Response:
        ser = AccountOpSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v, actor = ser.validated_data, actor_from(request)
        return _write(
            request,
            "withdrawal",
            _payload(v, "account_id"),
            lambda: svc.withdrawal(v["account_id"], v["money"], _common(v), actor),
            svc.rejecter(
                type=TxnType.WITHDRAWAL,
                amount=v["money"],
                actor=actor,
                debit_account_id=v["account_id"],
                reference=v["reference"],
                narrative=v["narrative"],
                channel=v["channel"],
            ),
        )


class TransferView(DataPlaneView):
    method_permissions = {"POST": TRANSACTIONS_POST}

    @_schema(
        "Internal transfer",
        TransferSerializer,
        TAG,
        {"source_account_id": "…", "target_account_id": "…", "amount": "200.00", "currency": "MRU"},
    )
    def post(self, request: Request) -> Response:
        ser = TransferSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v, actor = ser.validated_data, actor_from(request)
        return _write(
            request,
            "transfer",
            _payload(v, "source_account_id", "target_account_id"),
            lambda: svc.transfer(
                v["source_account_id"], v["target_account_id"], v["money"], _common(v), actor
            ),
            svc.rejecter(
                type=TxnType.TRANSFER,
                amount=v["money"],
                actor=actor,
                debit_account_id=v["source_account_id"],
                credit_account_id=v["target_account_id"],
                reference=v["reference"],
                narrative=v["narrative"],
                channel=v["channel"],
            ),
        )


class DisbursementView(DataPlaneView):
    method_permissions = {"POST": LOANS_DISBURSE}

    @_schema("Disburse a loan into a deposit account", DisbursementSerializer, LOAN_TAG)
    def post(self, request: Request, account_id: UUID) -> Response:
        ser = DisbursementSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v, actor = ser.validated_data, actor_from(request)
        payload = {**_payload(v, "target_account_id"), "loan_account_id": str(account_id)}
        return _write(
            request,
            "loan.disbursement",
            payload,
            lambda: svc.disburse(account_id, v["target_account_id"], v["money"], _common(v), actor),
            svc.rejecter(
                type=TxnType.DISBURSEMENT,
                amount=v["money"],
                actor=actor,
                debit_account_id=account_id,
                credit_account_id=v["target_account_id"],
                reference=v["reference"],
                narrative=v["narrative"],
                channel=v["channel"],
            ),
        )


class RepaymentView(DataPlaneView):
    method_permissions = {"POST": TRANSACTIONS_POST}

    @_schema("Repay a loan from a deposit account", RepaymentSerializer, LOAN_TAG)
    def post(self, request: Request, account_id: UUID) -> Response:
        ser = RepaymentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v, actor = ser.validated_data, actor_from(request)
        payload = {**_payload(v, "source_account_id"), "loan_account_id": str(account_id)}
        return _write(
            request,
            "loan.repayment",
            payload,
            lambda: svc.repay(v["source_account_id"], account_id, v["money"], _common(v), actor),
            svc.rejecter(
                type=TxnType.REPAYMENT,
                amount=v["money"],
                actor=actor,
                debit_account_id=v["source_account_id"],
                credit_account_id=account_id,
                reference=v["reference"],
                narrative=v["narrative"],
                channel=v["channel"],
            ),
        )


class HoldCreateView(DataPlaneView):
    method_permissions = {"POST": HOLDS_MANAGE}

    @_schema("Place a hold (authorization)", HoldSerializer, HOLD_TAG)
    def post(self, request: Request) -> Response:
        ser = HoldSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v, actor = ser.validated_data, actor_from(request)
        payload = {**_payload(v, "account_id"), "expires_in_seconds": v["expires_in_seconds"]}
        return _write(
            request,
            "hold.place",
            payload,
            lambda: svc.place_hold(
                v["account_id"], v["money"], v["expires_in_seconds"], _common(v), actor
            ),
            svc.rejecter(
                type=TxnType.HOLD,
                amount=v["money"],
                actor=actor,
                debit_account_id=v["account_id"],
                reference=v["reference"],
                narrative=v["narrative"],
                channel=v["channel"],
            ),
        )


class HoldCaptureView(DataPlaneView):
    method_permissions = {"POST": HOLDS_MANAGE}

    @_schema("Capture a hold (full or partial; remainder released)", CaptureSerializer, HOLD_TAG)
    def post(self, request: Request, hold_id: UUID) -> Response:
        ser = CaptureSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v, actor = ser.validated_data, actor_from(request)
        amount: Money | None = None
        if "amount" in v or "currency" in v:
            money = MoneyInputSerializer(
                data={"amount": v.get("amount"), "currency": v.get("currency")}
            )
            money.is_valid(raise_exception=True)
            amount = money.validated_data["money"]
        payload = {
            "hold_id": str(hold_id),
            "target_account_id": str(v["target_account_id"]),
            "amount": amount.to_wire() if amount else None,
            "currency": amount.currency if amount else None,
        }
        return _write(
            request,
            "hold.capture",
            payload,
            lambda: svc.capture_hold(hold_id, amount, v["target_account_id"], actor),
            _no_new_txn,
        )


class HoldReleaseView(DataPlaneView):
    method_permissions = {"POST": HOLDS_MANAGE}

    @_schema("Release a hold", None, HOLD_TAG)
    def post(self, request: Request, hold_id: UUID) -> Response:
        actor = actor_from(request)
        return _write(
            request,
            "hold.release",
            {"hold_id": str(hold_id)},
            lambda: svc.release_hold(hold_id, actor),
            _no_new_txn,
        )


class HoldDetailView(DataPlaneView):
    method_permissions = {"GET": TRANSACTIONS_READ}

    @extend_schema(
        tags=HOLD_TAG, summary="Get a hold's transaction", responses=TransactionOutSerializer
    )
    def get(self, request: Request, hold_id: UUID) -> Response:
        hold = Hold.objects.filter(id=hold_id).first()
        if hold is None:
            from next_core.platform.errors import NotFoundError

            raise NotFoundError("Hold not found.")
        return Response(svc.to_dict(svc.get_transaction(hold.transaction_id)))


class ReversalView(DataPlaneView):
    method_permissions = {"POST": TRANSACTIONS_REVERSE}

    @_schema("Reverse a POSTED transaction (mirror entries, linked)", ReversalSerializer, TAG)
    def post(self, request: Request, txn_id: UUID) -> Response:
        ser = ReversalSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        actor, reason = actor_from(request), ser.validated_data["reason"]
        return _write(
            request,
            "transaction.reversal",
            {"transaction_id": str(txn_id), "reason": reason},
            lambda: svc.reverse(txn_id, reason, actor),
            _no_new_txn,
        )


class TransactionListView(DataPlaneView):
    method_permissions = {"GET": TRANSACTIONS_READ}

    @extend_schema(
        tags=TAG,
        summary="List transactions",
        parameters=[
            OpenApiParameter("account_id", UUID, required=False),
            OpenApiParameter("type", str, required=False),
            OpenApiParameter("state", str, required=False),
        ],
        responses=TransactionOutSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        from django.db.models import Q

        from next_core.platform.errors import ValidationFailedError

        qs = BusinessTransaction.objects.all()
        account_id = request.query_params.get("account_id")
        if account_id:
            try:
                acc = UUID(account_id)
            except ValueError as exc:
                raise ValidationFailedError("account_id must be a UUID.") from exc
            qs = qs.filter(Q(debit_account_id=acc) | Q(credit_account_id=acc))
        for name in ("type", "state"):
            value = request.query_params.get(name)
            if value:
                qs = qs.filter(**{name: value[:24]})
        paginator = BoundedCursorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([svc.to_dict(t) for t in page or []])


class TransactionDetailView(DataPlaneView):
    method_permissions = {"GET": TRANSACTIONS_READ}

    @extend_schema(tags=TAG, summary="Get a transaction", responses=TransactionOutSerializer)
    def get(self, request: Request, txn_id: UUID) -> Response:
        return Response(svc.to_dict(svc.get_transaction(txn_id)))


class TransactionTransitionsView(DataPlaneView):
    method_permissions = {"GET": TRANSACTIONS_READ}

    @extend_schema(
        tags=TAG,
        summary="State-transition history (append-only)",
        responses={200: OBJ_LIST},
    )
    def get(self, request: Request, txn_id: UUID) -> Response:
        svc.get_transaction(txn_id)
        return Response(svc.transitions(txn_id))


class SimulateView(DataPlaneView):
    method_permissions = {"POST": TRANSACTIONS_READ}

    @extend_schema(
        tags=TAG,
        summary="Dry-run any operation against live state (always rolled back)",
        request=SimulateSerializer,
        responses={200: OBJ},
    )
    def post(self, request: Request) -> Response:
        from next_core.platform.errors import ValidationFailedError

        ser = SimulateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v, actor = ser.validated_data, actor_from(request)
        kind, money, common = v["type"], v["money"], _common(v)

        def need(*names: str) -> list[UUID]:
            missing = [n for n in names if not v.get(n)]
            if missing:
                raise ValidationFailedError(f"{kind} simulation requires: {', '.join(missing)}.")
            return [v[n] for n in names]

        work: svc.Work
        if kind in ("DEPOSIT", "WITHDRAWAL", "HOLD"):
            (acc,) = need("account_id")
            ids = [acc]
            if kind == "DEPOSIT":
                work = lambda: svc.deposit(acc, money, common, actor)  # noqa: E731
            elif kind == "WITHDRAWAL":
                work = lambda: svc.withdrawal(acc, money, common, actor)  # noqa: E731
            else:
                work = lambda: svc.place_hold(acc, money, v["expires_in_seconds"], common, actor)  # noqa: E731
        else:
            src, dst = need("source_account_id", "target_account_id")
            ids = [src, dst]
            fn = {"TRANSFER": svc.transfer, "DISBURSEMENT": svc.disburse, "REPAYMENT": svc.repay}[
                kind
            ]
            work = lambda: fn(src, dst, money, common, actor)  # noqa: E731

        def balances() -> list[UUID]:
            out: list[UUID] = []
            for account_id in ids:
                account = get_account(account_id)
                out.append(account.principal_balance_id)
            return out

        return Response(svc.simulate(work, balances))


class EodSerializer(StrictSerializer):
    business_date = serializers.DateField(required=False)


class EodView(DataPlaneView):
    method_permissions = {"POST": OPERATIONS_RUN}

    @extend_schema(
        tags=["Operations"],
        summary="Run EoD steps: hold expiry + interest accrual/capitalization (idempotent)",
        request=EodSerializer,
        responses={200: OBJ},
    )
    def post(self, request: Request) -> Response:
        ser = EodSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        on: date = ser.validated_data.get("business_date") or clock.business_date()
        actor = actor_from(request)
        expired = svc.expire_holds(actor)
        summary = svc.run_interest(on, actor)
        body: dict[str, Any] = {
            "business_date": on.isoformat(),
            "holds_expired": expired,
            "hold_reconciliation_findings": svc.reconcile_holds(),
            "interest": {
                "accounts_considered": summary.accounts_considered,
                "accrued": summary.accrued,
                "capitalized": summary.capitalized,
            },
        }
        return Response(body)
