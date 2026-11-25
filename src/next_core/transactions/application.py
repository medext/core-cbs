"""Transaction orchestration — the only caller of the ledger posting service.

Every financial operation runs as ONE database transaction:

    idempotency gate (INSERT … ON CONFLICT) → business transaction RECEIVED/VALIDATING →
    lock accounts (UUID order) → account state & product rules → fees → limits (locked
    counters) → ledger.post (locks balances in UUID order, funds check, entries, projections,
    outbox) → state AUTHORIZED → POSTED/HELD → store response on the idempotency record →
    COMMIT

A business rejection (insufficient funds, limit, account state, product rule…) rolls back
the savepoint holding every effect, then records a REJECTED transaction and a FAILED_FINAL
idempotency record with the problem body — a retry with the same key replays the same
answer (ADR-0006). Deadlocks/serialization failures are retried (bounded) as a whole.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import structlog
from django.db import OperationalError, connections, transaction

from next_core.accounts import application as accounts
from next_core.accounts.application import AccountSnapshot
from next_core.audit.service import record_event
from next_core.ledger import application as ledger
from next_core.ledger.domain import Direction, EntrySpec, HoldChange, PostingLine
from next_core.limits.application import consume as consume_limits
from next_core.platform import clock
from next_core.platform.actor import Actor
from next_core.platform.errors import (
    AccountStateInvalidError,
    AmountExceedsOutstandingError,
    ConflictStateError,
    CreditLimitExceededError,
    CurrencyMismatchError,
    DomainError,
    IdempotencyConflictError,
    MakerCheckerViolationError,
    NotFoundError,
    OperationNotAllowedError,
    ProductRuleViolationError,
    RequestInProgressError,
    ValidationFailedError,
)
from next_core.platform.money import Money
from next_core.platform.outbox.service import emit
from next_core.pricing.fees import FeeCharge, compute_fees
from next_core.pricing.interest import daily_accrual
from next_core.products.definition import BalanceSide, Capitalization, Operation
from next_core.products.expressions import ExpressionError, Value
from next_core.tenancy.context import current_tenant
from next_core.transactions.models import (
    TERMINAL_STATES,
    BusinessTransaction,
    Hold,
    HoldStatus,
    IdempotencyRecord,
    TransactionStateTransition,
    TxnState,
    TxnType,
)

SOURCE_TYPE = "TRANSACTION"
_jitter = secrets.SystemRandom()  # retry jitter (not security-relevant; avoids B311)
log = structlog.get_logger("next_core")
_DEADLOCK_CODES = frozenset({"40P01", "40001"})
_MAX_ATTEMPTS = 3
_SYSTEM_NS = uuid.UUID("6f1c6c1e-3c1a-4d43-9a39-6b6f2d9b7a10")

LEGAL: dict[str, frozenset[str]] = {
    TxnState.RECEIVED: frozenset({TxnState.VALIDATING}),
    TxnState.VALIDATING: frozenset({TxnState.REJECTED, TxnState.AUTHORIZED, TxnState.FAILED}),
    TxnState.AUTHORIZED: frozenset(
        {TxnState.HELD, TxnState.POSTED, TxnState.VOIDED, TxnState.FAILED}
    ),
    TxnState.HELD: frozenset({TxnState.POSTED, TxnState.VOIDED}),
    TxnState.POSTED: frozenset({TxnState.SETTLED, TxnState.REVERSED}),
}


@dataclass(frozen=True, slots=True)
class Idempotency:
    operation: str
    client_id: str
    key: str


@dataclass(frozen=True, slots=True)
class Outcome:
    status: int
    body: dict[str, Any]
    replayed: bool


def _alias() -> str:
    return current_tenant().db_alias


def _correlation_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("correlation_id", ""))


def request_hash(operation: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"operation": operation, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


# ------------------------------------------------------------------------- state machine


def _transition(txn: BusinessTransaction, to: str, actor: Actor, reason: str = "") -> None:
    if to not in LEGAL.get(txn.state, frozenset()):
        raise ConflictStateError(f"Transaction cannot move from {txn.state} to {to}.")
    TransactionStateTransition.objects.create(
        tenant_id=txn.tenant_id,
        transaction=txn,
        from_state=txn.state,
        to_state=to,
        reason=reason[:300],
        actor=actor.id,
    )
    previous = txn.state
    txn.state = to
    txn.save()
    emit(
        "transaction.state.changed",
        aggregate_type="transaction",
        aggregate_id=str(txn.id),
        payload={
            "transaction_id": str(txn.id),
            "type": txn.type,
            "from": previous,
            "to": to,
        },
    )


def _new_txn(
    *,
    txn_id: uuid.UUID | None = None,
    type: str,
    amount: Money,
    actor: Actor,
    debit_account_id: uuid.UUID | None = None,
    credit_account_id: uuid.UUID | None = None,
    reference: str = "",
    narrative: str = "",
    channel: str = "API",
    reversal_of: BusinessTransaction | None = None,
    value_date: date | None = None,
) -> BusinessTransaction:
    today = clock.business_date()
    txn = BusinessTransaction(
        id=txn_id or uuid.uuid4(),
        tenant_id=current_tenant().tenant_id,
        type=type,
        state=TxnState.RECEIVED,
        amount_minor=amount.amount_minor,
        currency=amount.currency,
        debit_account_id=debit_account_id,
        credit_account_id=credit_account_id,
        reference=reference[:64],
        narrative=narrative[:200],
        channel=channel[:20],
        business_date=today,
        value_date=value_date or today,
        reversal_of=reversal_of,
        initiated_by=actor.id,
    )
    txn.save()
    TransactionStateTransition.objects.create(
        tenant_id=txn.tenant_id,
        transaction=txn,
        from_state="",
        to_state=TxnState.RECEIVED,
        reason="intake",
        actor=actor.id,
    )
    _transition(txn, TxnState.VALIDATING, actor)
    return txn


# ------------------------------------------------------------------------- serialization


def _wire(minor: int, currency: str) -> str:
    return Money(minor, currency).to_wire()


def to_dict(txn: BusinessTransaction) -> dict[str, Any]:
    reversed_by = (
        BusinessTransaction.objects.filter(reversal_of_id=txn.id)
        .values_list("id", flat=True)
        .first()
    )
    hold = Hold.objects.filter(transaction_id=txn.id).first()
    body: dict[str, Any] = {
        "id": str(txn.id),
        "type": txn.type,
        "state": txn.state,
        "is_terminal": txn.state in TERMINAL_STATES,
        "funds_reserved": txn.state == TxnState.HELD,
        "amount": _wire(txn.amount_minor, txn.currency),
        "currency": txn.currency,
        "debit_account_id": str(txn.debit_account_id) if txn.debit_account_id else None,
        "credit_account_id": str(txn.credit_account_id) if txn.credit_account_id else None,
        "fees": txn.fees,
        "total_fees": _wire(
            sum(Money.from_wire(f["total"], f["currency"]).amount_minor for f in txn.fees),
            txn.currency,
        ),
        "reference": txn.reference,
        "narrative": txn.narrative,
        "channel": txn.channel,
        "business_date": txn.business_date.isoformat(),
        "value_date": txn.value_date.isoformat(),
        "journal_entry_ids": txn.journal_entry_ids,
        "product_versions": txn.product_versions,
        "reversal_of": str(txn.reversal_of_id) if txn.reversal_of_id else None,
        "reversed_by": str(reversed_by) if reversed_by else None,
        "rejection": (
            {"code": txn.rejection_code, "detail": txn.rejection_detail}
            if txn.state == TxnState.REJECTED
            else None
        ),
        "hold": (
            {
                "id": str(hold.id),
                "account_id": str(hold.account_id),
                "status": hold.status,
                "amount": _wire(hold.amount_minor, hold.currency),
                "captured_amount": _wire(hold.captured_minor, hold.currency),
                "expires_at": hold.expires_at.isoformat(),
            }
            if hold
            else None
        ),
        "created_at": txn.created_at.isoformat(),
    }
    return body


def transitions(txn_id: uuid.UUID) -> list[dict[str, Any]]:
    return [
        {
            "id": t.id,
            "from": t.from_state or None,
            "to": t.to_state,
            "reason": t.reason,
            "actor": t.actor,
            "occurred_at": t.occurred_at.isoformat(),
        }
        for t in TransactionStateTransition.objects.filter(transaction_id=txn_id).order_by("id")
    ]


def get_transaction(txn_id: uuid.UUID) -> BusinessTransaction:
    try:
        return BusinessTransaction.objects.get(id=txn_id)
    except BusinessTransaction.DoesNotExist as exc:
        raise NotFoundError("Transaction not found.") from exc


# ------------------------------------------------------------------------- idempotency


Work = Callable[[], BusinessTransaction]
OnReject = Callable[[DomainError], BusinessTransaction | None]


def execute_idempotent(
    idem: Idempotency, payload: dict[str, Any], work: Work, on_reject: OnReject
) -> Outcome:
    """Run ``work`` exactly once per idempotency scope; see module docstring."""
    ctx = current_tenant()
    if not idem.key or len(idem.key) > 128 or not idem.key.isprintable():
        raise ValidationFailedError("Idempotency-Key must be 1..128 printable characters.")
    digest = request_hash(idem.operation, payload)
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            with transaction.atomic(using=ctx.db_alias):
                with connections[ctx.db_alias].cursor() as cur:
                    cur.execute(
                        "INSERT INTO idempotency_record (tenant_id, operation, client_id, key, "
                        "request_hash, status, created_at) VALUES (%s, %s, %s, %s, %s, "
                        "'PROCESSING', now()) ON CONFLICT DO NOTHING RETURNING id",
                        [str(ctx.tenant_id), idem.operation, idem.client_id, idem.key, digest],
                    )
                    row = cur.fetchone()
                if row is None:
                    existing = IdempotencyRecord.objects.get(
                        operation=idem.operation, client_id=idem.client_id, key=idem.key
                    )
                    if existing.request_hash != digest:
                        raise IdempotencyConflictError(
                            "This Idempotency-Key was already used with a different payload."
                        )
                    if existing.status == "PROCESSING":  # pragma: no cover - async paths only
                        raise RequestInProgressError("A request with this key is in progress.")
                    if existing.response_status is None:  # pragma: no cover - defensive
                        raise RequestInProgressError("A request with this key is in progress.")
                    return Outcome(existing.response_status, existing.response_body or {}, True)

                record_id = row[0]
                try:
                    with transaction.atomic(using=ctx.db_alias):
                        txn = work()
                    status, body, final = 201, to_dict(txn), "COMPLETED"
                    txn_id: uuid.UUID | None = txn.id
                except DomainError as exc:
                    if exc.entry.retryable:
                        # Transient (e.g. REQUEST_IN_PROGRESS): never stored — the outer
                        # rollback removes the idempotency row so a retry with the same key
                        # re-executes (concurrency review N1).
                        raise
                    rejected = on_reject(exc)
                    body = exc.to_problem(_correlation_id())
                    if rejected is not None:
                        body["transaction_id"] = str(rejected.id)
                    status, final, txn_id = (
                        exc.entry.status,
                        "FAILED_FINAL",
                        (rejected.id if rejected else None),
                    )
                IdempotencyRecord.objects.filter(id=record_id).update(
                    status=final,
                    response_status=status,
                    response_body=body,
                    transaction_id=txn_id,
                    completed_at=clock.now(),
                )
                return Outcome(status, body, False)
        except OperationalError as exc:
            code = getattr(getattr(exc, "__cause__", None), "sqlstate", None)
            if code in _DEADLOCK_CODES and attempt < _MAX_ATTEMPTS:
                structlog.get_logger("next_core").warning(
                    "transactions.retry_after_db_conflict", sqlstate=code, attempt=attempt
                )
                time.sleep(_jitter.uniform(0.005, 0.05) * attempt)  # bounded, jittered backoff
                continue
            raise
    raise AssertionError("unreachable")  # pragma: no cover


def rejecter(
    *,
    type: str,
    amount: Money,
    actor: Actor,
    debit_account_id: uuid.UUID | None = None,
    credit_account_id: uuid.UUID | None = None,
    reference: str = "",
    narrative: str = "",
    channel: str = "API",
) -> OnReject:
    def on_reject(exc: DomainError) -> BusinessTransaction:
        txn = _new_txn(
            type=type,
            amount=amount,
            actor=actor,
            debit_account_id=debit_account_id,
            credit_account_id=credit_account_id,
            reference=reference,
            narrative=narrative,
            channel=channel,
        )
        txn.rejection_code = exc.code
        txn.rejection_detail = exc.detail[:300]
        _transition(txn, TxnState.REJECTED, actor, exc.code)
        return txn

    return on_reject


# ------------------------------------------------------------------------- product evaluation


def _env(
    snap: AccountSnapshot, operation: Operation, amount: Money, channel: str, today: date
) -> dict[str, Value]:
    balance = ledger.get_balance(snap.principal_balance_id)
    account = snap.account
    env: dict[str, Value] = {
        "amount": amount.to_major_decimal(),
        "currency": amount.currency,
        "operation": operation.value,
        "channel": channel,
        "kyc_level": Decimal(snap.kyc_level),
        "account_age_days": Decimal((today - account.opened_on).days),
        "days_to_maturity": Decimal(
            (account.maturity_date - today).days if account.maturity_date else -1
        ),
        "book_balance": Money(balance.book_balance, balance.currency).to_major_decimal(),
        "available_balance": Money(balance.available_balance, balance.currency).to_major_decimal(),
    }
    env.update(snap.definition.expression_env_params(amount.currency, snap.overrides))
    return env


def evaluate(
    snap: AccountSnapshot,
    operation: Operation,
    amount: Money,
    *,
    channel: str,
    today: date,
    consume: bool = True,
) -> list[FeeCharge]:
    """Product engine evaluation for one account leg: allowed operation, guards, fees, limits."""
    defn = snap.definition
    account = snap.account
    if amount.currency != account.currency:
        raise CurrencyMismatchError(
            f"Account {account.number} is in {account.currency}, not {amount.currency}."
        )
    if operation not in defn.allowed_operations:
        raise OperationNotAllowedError(
            f"Product {snap.product.product_code} does not allow {operation.value}."
        )
    env = _env(snap, operation, amount, channel, today)
    for rule in defn.operation_rules:
        if operation not in rule.operations:
            continue
        try:
            allowed = rule.condition.evaluate_bool(env)
        except ExpressionError as exc:
            log.warning("product.rule.evaluation_failed", rule=rule.code, error=str(exc))
            raise ProductRuleViolationError(
                f"Product rule {rule.code} could not be evaluated.", extra={"rule": rule.code}
            ) from exc
        if not allowed:
            raise ProductRuleViolationError(rule.message, extra={"rule": rule.code})
    fees = compute_fees(defn.fees, operation, amount, env)
    consume_limits(account.id, defn.limits, operation, amount, today, dry_run=not consume)
    return fees


def _fee_entries(snap: AccountSnapshot, fees: Sequence[FeeCharge], tag: str) -> list[EntrySpec]:
    specs: list[EntrySpec] = []
    gl = snap.definition.gl_mapping
    for i, fee in enumerate(fees, start=1):
        income = ledger.internal_balance(gl["fee_income"], fee.net.currency)
        lines = [
            PostingLine(snap.principal_balance_id, Direction.DEBIT, fee.total),
            PostingLine(income.id, Direction.CREDIT, fee.net),
        ]
        if fee.tax.is_positive:
            tax = ledger.internal_balance(gl["tax_payable"], fee.tax.currency)
            lines.append(PostingLine(tax.id, Direction.CREDIT, fee.tax))
        specs.append(
            EntrySpec(
                purpose=f"FEE{tag}{i}:{fee.code}"[:40],
                lines=tuple(lines),
                description=f"Fee {fee.code}",
                metadata={"fee_code": fee.code, "account_id": str(snap.id)},
            )
        )
    return specs


def _fee_json(snap: AccountSnapshot, fees: Sequence[FeeCharge]) -> list[dict[str, Any]]:
    return [
        {
            "code": f.code,
            "account_id": str(snap.id),
            "amount": f.net.to_wire(),
            "tax": f.tax.to_wire(),
            "total": f.total.to_wire(),
            "currency": f.net.currency,
        }
        for f in fees
    ]


def _check_first_deposit(snap: AccountSnapshot, amount: Money) -> None:
    balance = ledger.get_balance(snap.principal_balance_id)
    minimum = snap.definition.lifecycle.min_opening_amount.get(amount.currency, 0)
    if balance.last_entry_seq == 0 and amount.amount_minor < minimum:
        raise ProductRuleViolationError(
            f"The first deposit must be at least {Money(minimum, amount.currency)}.",
            extra={"rule": "MIN_OPENING_AMOUNT"},
        )


def _post(
    txn: BusinessTransaction,
    specs: Sequence[EntrySpec],
    *,
    holds: Sequence[HoldChange] = (),
    allow_overdraw: bool = False,
) -> ledger.PostingResult:
    result = ledger.post(
        ledger.PostingRequest(
            source_type=SOURCE_TYPE,
            source_id=txn.id,
            entries=tuple(specs),
            hold_changes=tuple(holds),
            business_date=txn.business_date,
            allow_overdraw=allow_overdraw,
        )
    )
    txn.journal_entry_ids = [*txn.journal_entry_ids, *[str(e.id) for e in result.entries]]
    return result


def _pin_versions(txn: BusinessTransaction, *snaps: AccountSnapshot) -> None:
    txn.product_versions = {
        str(s.id): {"product": s.product.product_code, "version": s.product.version} for s in snaps
    }


# ------------------------------------------------------------------------- operations


@dataclass(frozen=True, slots=True)
class CommonFields:
    reference: str = ""
    narrative: str = ""
    channel: str = "API"


def deposit(
    account_id: uuid.UUID,
    amount: Money,
    common: CommonFields,
    actor: Actor,
) -> BusinessTransaction:
    """Cash-in at a branch/agent: DR cash (asset) / CR customer principal."""
    today = clock.business_date()
    snap = accounts.lock_for_operation([account_id])[account_id]
    txn = _new_txn(
        type=TxnType.DEPOSIT,
        amount=amount,
        actor=actor,
        credit_account_id=account_id,
        reference=common.reference,
        narrative=common.narrative,
        channel=common.channel,
    )
    accounts.ensure_operable(snap, debit=False)
    fees = evaluate(snap, Operation.DEPOSIT, amount, channel=common.channel, today=today)
    _check_first_deposit(snap, amount)
    cash = ledger.internal_balance(snap.definition.gl_mapping["cash"], amount.currency)
    principal = EntrySpec(
        "PRINCIPAL",
        (
            PostingLine(cash.id, Direction.DEBIT, amount),
            PostingLine(snap.principal_balance_id, Direction.CREDIT, amount),
        ),
        description=common.narrative or "Deposit",
    )
    txn.fees = _fee_json(snap, fees)
    _pin_versions(txn, snap)
    _transition(txn, TxnState.AUTHORIZED, actor)
    _post(txn, [principal, *_fee_entries(snap, fees, "C")])
    accounts.touch_activity(snap.account, today)
    _transition(txn, TxnState.POSTED, actor)
    return txn


def withdrawal(
    account_id: uuid.UUID, amount: Money, common: CommonFields, actor: Actor
) -> BusinessTransaction:
    """Cash-out: DR customer principal / CR cash."""
    today = clock.business_date()
    snap = accounts.lock_for_operation([account_id])[account_id]
    txn = _new_txn(
        type=TxnType.WITHDRAWAL,
        amount=amount,
        actor=actor,
        debit_account_id=account_id,
        reference=common.reference,
        narrative=common.narrative,
        channel=common.channel,
    )
    accounts.ensure_operable(snap, debit=True)
    fees = evaluate(snap, Operation.WITHDRAWAL, amount, channel=common.channel, today=today)
    cash = ledger.internal_balance(snap.definition.gl_mapping["cash"], amount.currency)
    principal = EntrySpec(
        "PRINCIPAL",
        (
            PostingLine(snap.principal_balance_id, Direction.DEBIT, amount),
            PostingLine(cash.id, Direction.CREDIT, amount),
        ),
        description=common.narrative or "Withdrawal",
    )
    txn.fees = _fee_json(snap, fees)
    _pin_versions(txn, snap)
    _transition(txn, TxnState.AUTHORIZED, actor)
    _post(txn, [principal, *_fee_entries(snap, fees, "D")])
    accounts.touch_activity(snap.account, today)
    _transition(txn, TxnState.POSTED, actor)
    return txn


def _two_leg(
    txn_type: str,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    source_op: Operation,
    target_op: Operation,
    amount: Money,
    common: CommonFields,
    actor: Actor,
) -> BusinessTransaction:
    """DR source principal / CR target principal, with per-leg product evaluation.

    In ledger terms this single shape covers transfers (liability→liability), loan
    disbursements (DR loan asset ↑ / CR deposit ↑) and repayments (DR deposit ↓ / CR loan ↓)."""
    if source_id == target_id:
        raise ValidationFailedError("Source and target accounts must differ.")
    today = clock.business_date()
    snaps = accounts.lock_for_operation([source_id, target_id])
    src, dst = snaps[source_id], snaps[target_id]
    txn = _new_txn(
        type=txn_type,
        amount=amount,
        actor=actor,
        debit_account_id=source_id,
        credit_account_id=target_id,
        reference=common.reference,
        narrative=common.narrative,
        channel=common.channel,
    )
    accounts.ensure_operable(src, debit=True)
    accounts.ensure_operable(dst, debit=False)
    if src.account.currency != dst.account.currency:
        raise CurrencyMismatchError("Cross-currency transfers are not supported (OD-4).")
    src_fees = evaluate(src, source_op, amount, channel=common.channel, today=today)
    dst_fees = evaluate(dst, target_op, amount, channel=common.channel, today=today)

    if txn_type == TxnType.DISBURSEMENT:
        defn = src.definition
        if defn.credit_limit_parameter is None:  # pragma: no cover - definition-validated
            raise OperationNotAllowedError("Lending product without a credit limit.")
        limit = defn.money_param(defn.credit_limit_parameter, amount.currency, src.overrides)
        outstanding = ledger.get_balance(src.principal_balance_id).book_balance
        charged = amount.amount_minor + sum(f.total.amount_minor for f in src_fees)
        if outstanding + charged > limit:
            raise CreditLimitExceededError(
                f"Disbursement would exceed the credit limit {Money(limit, amount.currency)} "
                f"(outstanding {Money(outstanding, amount.currency)})."
            )
    if txn_type == TxnType.REPAYMENT:
        outstanding = ledger.get_balance(dst.principal_balance_id).book_balance
        if amount.amount_minor > outstanding:
            raise AmountExceedsOutstandingError(
                f"Repayment {amount} exceeds the outstanding principal "
                f"{Money(outstanding, amount.currency)}."
            )

    principal = EntrySpec(
        "PRINCIPAL",
        (
            PostingLine(src.principal_balance_id, Direction.DEBIT, amount),
            PostingLine(dst.principal_balance_id, Direction.CREDIT, amount),
        ),
        description=common.narrative or txn_type.title(),
    )
    txn.fees = _fee_json(src, src_fees) + _fee_json(dst, dst_fees)
    _pin_versions(txn, src, dst)
    _transition(txn, TxnState.AUTHORIZED, actor)
    _post(txn, [principal, *_fee_entries(src, src_fees, "D"), *_fee_entries(dst, dst_fees, "C")])
    accounts.touch_activity(src.account, today)
    accounts.touch_activity(dst.account, today)
    _transition(txn, TxnState.POSTED, actor)
    return txn


def transfer(
    source_id: uuid.UUID, target_id: uuid.UUID, amount: Money, common: CommonFields, actor: Actor
) -> BusinessTransaction:
    return _two_leg(
        TxnType.TRANSFER,
        source_id,
        target_id,
        Operation.TRANSFER_OUT,
        Operation.TRANSFER_IN,
        amount,
        common,
        actor,
    )


def disburse(
    loan_id: uuid.UUID, target_id: uuid.UUID, amount: Money, common: CommonFields, actor: Actor
) -> BusinessTransaction:
    return _two_leg(
        TxnType.DISBURSEMENT,
        loan_id,
        target_id,
        Operation.DISBURSEMENT,
        Operation.TRANSFER_IN,
        amount,
        common,
        actor,
    )


def repay(
    source_id: uuid.UUID, loan_id: uuid.UUID, amount: Money, common: CommonFields, actor: Actor
) -> BusinessTransaction:
    return _two_leg(
        TxnType.REPAYMENT,
        source_id,
        loan_id,
        Operation.TRANSFER_OUT,
        Operation.REPAYMENT,
        amount,
        common,
        actor,
    )


# ------------------------------------------------------------------------- holds

MAX_HOLD_SECONDS = 30 * 24 * 3600


def place_hold(
    account_id: uuid.UUID,
    amount: Money,
    expires_in_seconds: int,
    common: CommonFields,
    actor: Actor,
) -> BusinessTransaction:
    if not 60 <= expires_in_seconds <= MAX_HOLD_SECONDS:
        raise ValidationFailedError("expires_in_seconds must be between 60 and 2592000.")
    today = clock.business_date()
    snap = accounts.lock_for_operation([account_id])[account_id]
    txn = _new_txn(
        type=TxnType.HOLD,
        amount=amount,
        actor=actor,
        debit_account_id=account_id,
        reference=common.reference,
        narrative=common.narrative,
        channel=common.channel,
    )
    accounts.ensure_operable(snap, debit=True)
    evaluate(snap, Operation.HOLD, amount, channel=common.channel, today=today)
    _pin_versions(txn, snap)
    _transition(txn, TxnState.AUTHORIZED, actor)
    _post(
        txn, [], holds=[HoldChange(snap.principal_balance_id, amount.amount_minor, amount.currency)]
    )
    Hold.objects.create(
        tenant_id=txn.tenant_id,
        account_id=account_id,
        balance_id=snap.principal_balance_id,
        transaction=txn,
        amount_minor=amount.amount_minor,
        currency=amount.currency,
        expires_at=clock.now() + timedelta(seconds=expires_in_seconds),
    )
    _transition(txn, TxnState.HELD, actor)
    return txn


def _hold_for_update(
    hold_id: uuid.UUID, extra_accounts: Sequence[uuid.UUID] = ()
) -> tuple[Hold, dict[uuid.UUID, AccountSnapshot], BusinessTransaction]:
    """Lock order: accounts (UUID) → hold row → business transaction row."""
    peek = Hold.objects.filter(id=hold_id).values_list("account_id", flat=True).first()
    if peek is None:
        raise NotFoundError("Hold not found.")
    snaps = accounts.lock_for_operation([peek, *extra_accounts])
    hold = Hold.objects.select_for_update().get(id=hold_id)
    txn = BusinessTransaction.objects.select_for_update().get(id=hold.transaction_id)
    return hold, snaps, txn


def capture_hold(
    hold_id: uuid.UUID, amount: Money | None, target_id: uuid.UUID, actor: Actor
) -> BusinessTransaction:
    """HELD → POSTED: posts the captured amount to ``target_id`` and releases the whole hold
    in the same ledger call (partial capture releases the remainder atomically)."""
    hold, snaps, txn = _hold_for_update(hold_id, [target_id])
    if hold.status != HoldStatus.ACTIVE:
        raise ConflictStateError(f"Hold is {hold.status}.")
    if hold.expires_at <= clock.now():
        raise ConflictStateError("Hold has expired.")
    captured = amount or Money(hold.amount_minor, hold.currency)
    if captured.currency != hold.currency:
        raise CurrencyMismatchError("Capture currency differs from the hold currency.")
    if not 0 < captured.amount_minor <= hold.amount_minor:
        raise ValidationFailedError("Capture amount must be > 0 and ≤ the held amount.")
    if target_id == hold.account_id:
        raise ValidationFailedError("Capture target must differ from the held account.")
    src, dst = snaps[hold.account_id], snaps[target_id]
    accounts.ensure_operable(src, debit=True)
    accounts.ensure_operable(dst, debit=False)
    dst_fees = evaluate(
        dst, Operation.TRANSFER_IN, captured, channel=txn.channel, today=clock.business_date()
    )
    entry = EntrySpec(
        "CAPTURE",
        (
            PostingLine(src.principal_balance_id, Direction.DEBIT, captured),
            PostingLine(dst.principal_balance_id, Direction.CREDIT, captured),
        ),
        description="Hold capture",
    )
    _post(
        txn,
        [entry, *_fee_entries(dst, dst_fees, "C")],
        holds=[HoldChange(hold.balance_id, -hold.amount_minor, hold.currency)],
    )
    hold.status = HoldStatus.CAPTURED
    hold.captured_minor = captured.amount_minor
    hold.save(update_fields=["status", "captured_minor", "updated_at"])
    txn.credit_account_id = target_id
    txn.fees = txn.fees + _fee_json(dst, dst_fees)
    _transition(txn, TxnState.POSTED, actor, f"captured {captured.to_wire()}")
    return txn


def release_hold(hold_id: uuid.UUID, actor: Actor, *, expired: bool = False) -> BusinessTransaction:
    hold, _snaps, txn = _hold_for_update(hold_id)
    if hold.status != HoldStatus.ACTIVE:
        raise ConflictStateError(f"Hold is {hold.status}.")
    _post(txn, [], holds=[HoldChange(hold.balance_id, -hold.amount_minor, hold.currency)])
    hold.status = HoldStatus.EXPIRED if expired else HoldStatus.RELEASED
    hold.save(update_fields=["status", "updated_at"])
    _transition(txn, TxnState.VOIDED, actor, "expired" if expired else "released")
    return txn


def expire_holds(actor: Actor, batch: int = 500) -> int:
    """Idempotent sweep: every ACTIVE hold past expiry → EXPIRED (one DB transaction each)."""
    due = list(
        Hold.objects.filter(status=HoldStatus.ACTIVE, expires_at__lte=clock.now())
        .order_by("expires_at")
        .values_list("id", flat=True)[:batch]
    )
    done = 0
    for hold_id in due:
        try:
            with transaction.atomic(using=_alias()):
                release_hold(hold_id, actor, expired=True)
            done += 1
        except ConflictStateError:
            continue  # raced with a capture/release — already terminal
    return done


def reconcile_holds() -> list[dict[str, Any]]:
    """held_amount projection ≡ Σ ACTIVE holds per balance (ledger review C6)."""
    from django.db.models import Sum

    active = {
        row["balance_id"]: row["total"]
        for row in Hold.objects.filter(status=HoldStatus.ACTIVE)
        .values("balance_id")
        .annotate(total=Sum("amount_minor"))
    }
    findings: list[dict[str, Any]] = []
    for account_id, principal_id in accounts.principal_balances():
        held = ledger.get_balance(principal_id).held_amount
        expected = active.get(principal_id, 0)
        if held != expected:
            findings.append(
                {
                    "kind": "HELD_AMOUNT_MISMATCH",
                    "account_id": str(account_id),
                    "projection": held,
                    "active_holds": expected,
                }
            )
    return findings


# ------------------------------------------------------------------------- reversal

_REVERSIBLE = frozenset(
    {
        TxnType.DEPOSIT,
        TxnType.WITHDRAWAL,
        TxnType.TRANSFER,
        TxnType.HOLD,
        TxnType.DISBURSEMENT,
        TxnType.REPAYMENT,
    }
)


def reverse(original_id: uuid.UUID, reason: str, actor: Actor) -> BusinessTransaction:
    """POSTED → REVERSED via a linked REVERSAL transaction whose entries mirror every entry
    of the original (principal and fees). Limit consumption is not refunded (conservative)."""
    peek = (
        BusinessTransaction.objects.filter(id=original_id)
        .values("debit_account_id", "credit_account_id")
        .first()
    )
    if peek is None:
        raise NotFoundError("Transaction not found.")
    account_ids = [a for a in (peek["debit_account_id"], peek["credit_account_id"]) if a]
    snaps = accounts.lock_for_operation(account_ids)
    original = BusinessTransaction.objects.select_for_update().get(id=original_id)
    locked_now = {a for a in (original.debit_account_id, original.credit_account_id) if a}
    if not locked_now <= set(snaps):
        # A concurrent capture attached a new account after our first read: we do not hold
        # its lock (and must not take it out of order). Retryable by the client.
        raise RequestInProgressError(
            "The transaction changed concurrently; retry the reversal with the same key."
        )
    if original.type not in _REVERSIBLE:
        raise ConflictStateError(f"{original.type} transactions are not reversible via the API.")
    if original.state != TxnState.POSTED:
        raise ConflictStateError(
            f"Only POSTED transactions can be reversed (state {original.state})."
        )
    if actor.id == original.initiated_by:
        raise MakerCheckerViolationError(
            "The initiator of a transaction cannot reverse it (four-eyes rule)."
        )
    for snap in snaps.values():
        if snap.account.status == "CLOSED":
            raise AccountStateInvalidError(f"Account {snap.account.number} is closed.")
    txn = _new_txn(
        type=TxnType.REVERSAL,
        amount=Money(original.amount_minor, original.currency),
        actor=actor,
        debit_account_id=original.credit_account_id,
        credit_account_id=original.debit_account_id,
        narrative=reason,
        reversal_of=original,
    )
    specs = ledger.reversal_specs([uuid.UUID(e) for e in original.journal_entry_ids])
    _transition(txn, TxnState.AUTHORIZED, actor)
    _post(txn, specs, allow_overdraw=True)
    _transition(txn, TxnState.POSTED, actor, reason)
    _transition(original, TxnState.REVERSED, actor, f"reversed by {txn.id}")
    record_event(
        operation="transaction.reversed",
        resource_type="transaction",
        resource_id=str(original.id),
        actor=actor.id,
        actor_type=actor.type,
        payload={"reversal_id": str(txn.id), "reason": reason[:200]},
    )
    return txn


# ------------------------------------------------------------------------- interest


@dataclass(frozen=True, slots=True)
class InterestRunSummary:
    business_date: date
    accounts_considered: int
    accrued: int
    capitalized: int
    skipped: int  # retained for API compatibility; always 0 since day-by-day catch-up


def _system_txn_id(account_id: uuid.UUID, on: date, kind: str) -> uuid.UUID:
    return uuid.uuid5(
        _SYSTEM_NS, f"{current_tenant().tenant_id}:{account_id}:{on.isoformat()}:{kind}"
    )


def _increase_line(balance: ledger.BalanceView, amount: Money) -> PostingLine:
    return PostingLine(balance.id, Direction(balance.normal_side), amount)


def _decrease_line(balance: ledger.BalanceView, amount: Money) -> PostingLine:
    opposite = Direction.CREDIT if balance.normal_side == "DEBIT" else Direction.DEBIT
    return PostingLine(balance.id, opposite, amount)


MAX_CATCH_UP_DAYS = 400


def _check_not_future(on: date) -> None:
    if on > clock.business_date():
        raise ValidationFailedError(
            "Interest cannot be accrued or capitalized for a future business date."
        )


def _accrue_day(snap: AccountSnapshot, day: date, actor: Actor) -> bool:
    """One day's accrual on the principal book balance *as of* ``day`` (value-dated)."""
    defn = snap.definition
    if defn.interest is None or snap.account.interest_balance_id is None:  # pragma: no cover
        raise ConflictStateError("Account has no interest configuration.")
    txn_id = _system_txn_id(snap.id, day, "ACCRUAL")
    if BusinessTransaction.objects.filter(id=txn_id).exists():
        return False
    principal_id = snap.principal_balance_id
    currency = snap.account.currency
    as_of = ledger.book_balance_as_of(principal_id, day)
    rate = Decimal(defn.param_value(defn.interest.rate_parameter, snap.overrides))
    minor = daily_accrual(
        as_of,
        rate,
        defn.interest.day_count,
        day,
        defn.interest.rounding,
        defn.interest.minimum_balance.get(currency, 0),
    )
    if minor <= 0:
        return False
    amount = Money(minor, currency)
    accrued_bal = ledger.get_balance(snap.account.interest_balance_id)
    is_liability = defn.balance_side == BalanceSide.LIABILITY
    counter_gl = defn.gl_mapping["interest_expense" if is_liability else "interest_income"]
    counter = ledger.internal_balance(counter_gl, currency)
    txn = _new_txn(
        txn_id=txn_id,
        type=TxnType.INTEREST_ACCRUAL,
        amount=amount,
        actor=actor,
        credit_account_id=snap.id,
        channel="SYSTEM",
        narrative=f"Interest accrual {day.isoformat()}",
        value_date=day,
    )
    # Accrued balance grows on its normal side; the P&L counterpart takes the other side.
    lines = (
        _increase_line(accrued_bal, amount),
        PostingLine(counter.id, Direction.DEBIT if is_liability else Direction.CREDIT, amount),
    )
    _pin_versions(txn, snap)
    _transition(txn, TxnState.AUTHORIZED, actor)
    _post(
        txn,
        [
            EntrySpec(
                "ACCRUAL",
                lines,
                description=f"Interest accrual {day.isoformat()}",
                value_date=day,
                metadata={
                    "rate": str(rate),
                    "day_count": defn.interest.day_count.value,
                    "basis_book_balance_minor": as_of,
                },
            )
        ],
    )
    _transition(txn, TxnState.POSTED, actor)
    return True


def accrue_interest_for(account_id: uuid.UUID, on: date, actor: Actor) -> int:
    """Accrue day by day, in order, from the account's checkpoint up to ``on`` (inclusive).

    Guarantees (ledger review B1): never for a future date; each day once (per-account
    ``interest_accrued_through`` checkpoint + deterministic txn id); the basis is the
    principal book balance as of that day (value dates ≤ day); entries carry value_date =
    day; accrual stops the day before maturity. Returns the number of days posted."""
    _check_not_future(on)
    posted = 0
    for _ in range(MAX_CATCH_UP_DAYS + 1):
        # One DB transaction per day (concurrency review N2): shared P&L rows are locked only
        # for one day's posting; checkpoint + deterministic txn ids make re-runs safe.
        with transaction.atomic(using=_alias()):
            snap = accounts.lock_for_operation([account_id])[account_id]
            account, defn = snap.account, snap.definition
            if (
                account.status == "CLOSED"
                or defn.interest is None
                or account.interest_balance_id is None
            ):
                return posted
            day = (
                account.interest_accrued_through + timedelta(days=1)
                if account.interest_accrued_through
                else account.opened_on
            )
            end = on
            if account.maturity_date is not None:
                end = min(end, account.maturity_date - timedelta(days=1))
            if day > end:
                return posted
            if posted == 0 and (end - day).days >= MAX_CATCH_UP_DAYS:
                raise ConflictStateError(
                    f"Accrual is {(end - day).days + 1} days behind; catch up in ≤ "
                    f"{MAX_CATCH_UP_DAYS}-day runs."
                )
            # Capitalizations due on/before this day go first (compounding is applied in
            # date order even during a catch-up).
            for due in _capitalization_dates(snap, account.interest_capitalized_through, day):
                _capitalize_one(snap, due, actor)
            posted += int(_accrue_day(snap, day, actor))
            accounts.mark_interest_accrued(account, day)
    return posted  # pragma: no cover - bounded by the catch-up guard


def _capitalization_dates(snap: AccountSnapshot, after: date | None, on: date) -> list[date]:
    """Due capitalization dates in (after, on], in order (catch-up of missed dates)."""
    defn, account = snap.definition, snap.account
    if defn.interest is None:  # pragma: no cover - caller checks
        return []
    if defn.interest.capitalization == Capitalization.AT_MATURITY:
        due = account.maturity_date
        return [due] if due is not None and due <= on and (after is None or due > after) else []
    if defn.interest.capitalization != Capitalization.MONTHLY:
        return []
    first = after or account.opened_on
    d = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    out: list[date] = []
    while d <= on:
        out.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def _capitalize_one(snap: AccountSnapshot, d: date, actor: Actor) -> bool:
    """Capitalize the accrued figure with value_date < d (caller holds the account lock and
    has checked accrual ran through d - 1). Advances the checkpoint to d."""
    account = snap.account
    if account.interest_balance_id is None:  # pragma: no cover - caller checks
        return False
    posted = False
    amount_minor = ledger.book_balance_as_of(account.interest_balance_id, d - timedelta(days=1))
    txn_id = _system_txn_id(account.id, d, "CAPITALIZATION")
    if amount_minor > 0 and not BusinessTransaction.objects.filter(id=txn_id).exists():
        accrued_bal = ledger.get_balance(account.interest_balance_id)
        principal = ledger.get_balance(snap.principal_balance_id)
        amount = Money(amount_minor, accrued_bal.currency)
        txn = _new_txn(
            txn_id=txn_id,
            type=TxnType.INTEREST_CAPITALIZATION,
            amount=amount,
            actor=actor,
            credit_account_id=account.id,
            channel="SYSTEM",
            narrative=f"Interest capitalization {d.isoformat()}",
            value_date=d,
        )
        lines = (_decrease_line(accrued_bal, amount), _increase_line(principal, amount))
        _pin_versions(txn, snap)
        _transition(txn, TxnState.AUTHORIZED, actor)
        _post(
            txn,
            [
                EntrySpec(
                    "CAPITALIZATION", lines, description="Interest capitalization", value_date=d
                )
            ],
        )
        _transition(txn, TxnState.POSTED, actor)
        posted = True
    accounts.mark_interest_capitalized(account, d)
    return posted


def capitalize_interest_for(account_id: uuid.UUID, on: date, actor: Actor) -> int:
    """Capitalize per policy for every due date up to ``on``, in order (MONTHLY: each 1st;
    AT_MATURITY: the maturity date). Resumable (``interest_capitalized_through`` checkpoint)
    and never early: the amount for date d is the accrued figure with value_date < d, and d
    is processed only once accrual has run through d - 1 (ledger review condition 1).
    One DB transaction per due date. Returns the number of capitalizations posted."""
    _check_not_future(on)
    posted = 0
    while True:
        with transaction.atomic(using=_alias()):
            snap = accounts.lock_for_operation([account_id])[account_id]
            account, defn = snap.account, snap.definition
            if (
                account.status == "CLOSED"
                or defn.interest is None
                or account.interest_balance_id is None
            ):
                return posted
            due = _capitalization_dates(snap, account.interest_capitalized_through, on)
            if not due:
                return posted
            d = due[0]
            accrued_through = account.interest_accrued_through
            needed = d - timedelta(days=1)
            if account.maturity_date is not None and d >= account.maturity_date:
                needed = account.maturity_date - timedelta(days=1)  # accrual stops there
            if needed >= account.opened_on and (
                accrued_through is None or accrued_through < needed
            ):
                return posted  # accrue first; capitalization waits (never early, never partial)
            posted += int(_capitalize_one(snap, d, actor))


def run_interest(on: date, actor: Actor) -> InterestRunSummary:
    """EoD step: accrue (catching up day by day) then capitalize, per interest-bearing
    account. Idempotent and resumable: per-account DB transactions, checkpoints and
    deterministic business-transaction ids."""
    _check_not_future(on)
    ids = accounts.interest_bearing_accounts()
    accrued = capitalized = 0
    for account_id in ids:
        accrued += accrue_interest_for(account_id, on, actor)
        capitalized += capitalize_interest_for(account_id, on, actor)
    return InterestRunSummary(on, len(ids), accrued, capitalized, 0)


# ------------------------------------------------------------------------- simulation


class _SimulationRollbackError(Exception):
    pass


def simulate(work: Work, balance_ids: Callable[[], list[uuid.UUID]]) -> dict[str, Any]:
    """Execute the real flow (same locks, rules, fees, limits, funds checks) inside a
    transaction that is always rolled back. Nothing persists; no event leaves the outbox."""
    result: dict[str, Any] = {}
    try:
        with transaction.atomic(using=_alias()):
            txn = work()
            result = {
                "outcome": "WOULD_POST"
                if txn.state == TxnState.POSTED
                else f"WOULD_BE_{txn.state}",
                "transaction": to_dict(txn),
                "balances_after": [_balance_dict(ledger.get_balance(bid)) for bid in balance_ids()],
            }
            raise _SimulationRollbackError
    except _SimulationRollbackError:
        return result
    except DomainError as exc:
        return {"outcome": "WOULD_BE_REJECTED", "error": exc.to_problem(_correlation_id())}


def _balance_dict(b: ledger.BalanceView) -> dict[str, Any]:
    return {
        "balance_id": str(b.id),
        "purpose": b.purpose,
        "currency": b.currency,
        "book_balance": _wire(b.book_balance, b.currency),
        "available_balance": _wire(b.available_balance, b.currency),
        "held_amount": _wire(b.held_amount, b.currency),
    }
