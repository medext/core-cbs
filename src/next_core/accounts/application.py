"""Accounts application services: opening, lifecycle & blocks, and the locking port used by
the transactions context.

Lock discipline (docs/architecture/idempotency-concurrency.md): every financial operation
locks its account rows FIRST (``lock_for_operation``, UUID order), then limit counters, then
ledger balances (UUID order). Closure takes the same account lock, so "closure vs incoming
posting" is serialized: either the posting commits first (and closure sees a non-zero
balance) or closure commits first (and the posting sees CLOSED).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from django.db import connections, transaction

from next_core.accounts.models import Account, AccountStatus, AccountStatusChange
from next_core.audit.service import record_event
from next_core.ledger import application as ledger
from next_core.parties.application import party_for_account_opening
from next_core.platform import clock
from next_core.platform.actor import Actor
from next_core.platform.errors import (
    AccountStateInvalidError,
    ConflictStateError,
    KycLevelInsufficientError,
    NotFoundError,
    PartyStateInvalidError,
    ValidationFailedError,
)
from next_core.platform.money import Money
from next_core.platform.outbox.service import emit
from next_core.products.application import ResolvedVersion, active_version, resolve_version
from next_core.products.definition import (
    BalanceSide,
    ProductDefinition,
    overrides_from_json,
    overrides_to_json,
    validate_overrides,
)
from next_core.tenancy.context import current_tenant


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    """Locked view handed to the transactions context."""

    account: Account
    product: ResolvedVersion
    overrides: dict[str, Any]
    kyc_level: int

    @property
    def definition(self) -> ProductDefinition:
        return self.product.definition

    @property
    def id(self) -> UUID:
        return self.account.id

    @property
    def principal_balance_id(self) -> UUID:
        return self.account.principal_balance_id


def _alias() -> str:
    return current_tenant().db_alias


def _next_number() -> str:
    with connections[_alias()].cursor() as cur:
        cur.execute("SELECT nextval('account_number_seq')")
        seq = int(cur.fetchone()[0])
    body = f"{seq:010d}"
    check = 98 - (int(body) * 100) % 97
    return f"{body}{check:02d}"


def valid_account_number(number: str) -> bool:
    return len(number) == 12 and number.isdigit() and int(number) % 97 == 1


def _history(account: Account, from_status: str, reason: str, actor: Actor) -> None:
    AccountStatusChange.objects.create(
        tenant_id=account.tenant_id,
        account=account,
        from_status=from_status,
        to_status=account.status,
        debit_blocked=account.debit_blocked,
        credit_blocked=account.credit_blocked,
        reason=reason[:300],
        actor=actor.id,
    )


def open_account(
    *,
    party_id: UUID,
    product_id: UUID,
    currency: str,
    parameter_overrides: dict[str, Any] | None,
    nickname: str,
    actor: Actor,
) -> Account:
    ctx = current_tenant()
    party = party_for_account_opening(party_id)
    if party.status != "ACTIVE":
        raise PartyStateInvalidError(f"Party is {party.status}; accounts require an ACTIVE party.")
    product = active_version(product_id)
    defn = product.definition
    if currency not in defn.currencies:
        raise ValidationFailedError(f"Product {product.product_code} does not support {currency}.")
    if party.kyc_level < defn.lifecycle.min_kyc_level:
        raise KycLevelInsufficientError(
            f"Product {product.product_code} requires KYC level "
            f"{defn.lifecycle.min_kyc_level}; party has {party.kyc_level}."
        )
    overrides = validate_overrides(defn, parameter_overrides, currency)
    today = clock.business_date()

    maturity: date | None = None
    if defn.lifecycle.term_parameter:
        days = int(defn.param_value(defn.lifecycle.term_parameter, overrides))
        if days < 1:
            raise ValidationFailedError("Term must be at least one day.")
        maturity = today + timedelta(days=days)

    is_liability = defn.balance_side == BalanceSide.LIABILITY
    overdraft = (
        defn.money_param(defn.overdraft_parameter, currency, overrides)
        if defn.overdraft_parameter
        else 0
    )
    with transaction.atomic(using=_alias()):
        account = Account(
            tenant_id=ctx.tenant_id,
            number=_next_number(),
            party_id=party_id,
            product_id=product.product_id,
            product_version_id=product.version_id,
            product_code=product.product_code,
            category=defn.category.value,
            balance_side=defn.balance_side.value,
            currency=currency,
            parameter_overrides=overrides_to_json(defn, overrides),
            nickname=nickname[:80],
            opened_on=today,
            maturity_date=maturity,
        )
        principal = ledger.open_balance(
            gl_code=defn.gl_mapping["principal"],
            currency=currency,
            owner_id=account.id,
            purpose="PRINCIPAL",
            funds_enforced=is_liability,
            overdraft_limit=overdraft,
        )
        account.principal_balance_id = principal.id
        if defn.interest is not None:
            accrued = ledger.open_balance(
                gl_code=defn.gl_mapping["accrued_interest"],
                currency=currency,
                owner_id=account.id,
                purpose="ACCRUED_INTEREST",
            )
            account.interest_balance_id = accrued.id
        account.save()
        _history(account, "", "opened", actor)
        record_event(
            operation="account.opened",
            resource_type="account",
            resource_id=str(account.id),
            actor=actor.id,
            actor_type=actor.type,
            payload={
                "product": product.product_code,
                "version": product.version,
                "currency": currency,
            },
        )
        emit(
            "account.opened",
            aggregate_type="account",
            aggregate_id=str(account.id),
            payload={
                "account_id": str(account.id),
                "number": account.number,
                "party_id": str(party_id),
                "product_code": product.product_code,
                "product_version": product.version,
                "currency": currency,
            },
        )
    return account


def get_account(account_id: UUID) -> Account:
    try:
        return Account.objects.get(id=account_id)
    except Account.DoesNotExist as exc:
        raise NotFoundError("Account not found.") from exc


def snapshot(account: Account) -> AccountSnapshot:
    product = resolve_version(account.product_version_id)
    party = party_for_account_opening(account.party_id)
    return AccountSnapshot(
        account=account,
        product=product,
        overrides=overrides_from_json(product.definition, account.parameter_overrides),
        kyc_level=party.kyc_level,
    )


def lock_for_operation(account_ids: Sequence[UUID]) -> dict[UUID, AccountSnapshot]:
    """SELECT … FOR UPDATE on the accounts (UUID order). Caller must hold a transaction."""
    if not connections[_alias()].in_atomic_block:
        raise RuntimeError("lock_for_operation requires an enclosing transaction.")
    wanted = sorted(set(account_ids))
    rows = list(Account.objects.select_for_update().filter(id__in=wanted).order_by("id"))
    if len(rows) != len(wanted):
        raise NotFoundError("Account not found.")
    return {a.id: snapshot(a) for a in rows}


def touch_activity(account: Account, on: date) -> None:
    """Record customer activity (dormancy input). Caller holds the account lock."""
    if account.last_activity_on != on:
        account.last_activity_on = on
        account.save(update_fields=["last_activity_on", "updated_at"])


def ensure_operable(snap: AccountSnapshot, *, debit: bool) -> None:
    a = snap.account
    if a.status != AccountStatus.ACTIVE:
        raise AccountStateInvalidError(f"Account {a.number} is {a.status}.")
    if debit and a.debit_blocked:
        raise AccountStateInvalidError(f"Account {a.number} is blocked for debits.")
    if not debit and a.credit_blocked:
        raise AccountStateInvalidError(f"Account {a.number} is blocked for credits.")


_TRANSITIONS: dict[str, set[str]] = {
    AccountStatus.ACTIVE: {AccountStatus.FROZEN, AccountStatus.DORMANT, AccountStatus.CLOSED},
    AccountStatus.FROZEN: {AccountStatus.ACTIVE, AccountStatus.CLOSED},
    AccountStatus.DORMANT: {AccountStatus.ACTIVE, AccountStatus.CLOSED},
    AccountStatus.CLOSED: set(),
}


def _locked(account_id: UUID) -> Account:
    account = Account.objects.select_for_update().filter(id=account_id).first()
    if account is None:
        raise NotFoundError("Account not found.")
    return account


def change_status(account_id: UUID, new_status: str, reason: str, actor: Actor) -> Account:
    if new_status == AccountStatus.CLOSED:
        return close_account(account_id, reason, actor)
    with transaction.atomic(using=_alias()):
        account = _locked(account_id)
        if new_status not in _TRANSITIONS[account.status]:
            raise ConflictStateError(f"Account cannot move from {account.status} to {new_status}.")
        old = account.status
        account.status = new_status
        account.version += 1
        account.save(update_fields=["status", "version", "updated_at"])
        _history(account, old, reason, actor)
        _status_evidence(account, old, reason, actor)
    return account


def set_blocks(
    account_id: UUID, *, debit: bool, credit: bool, reason: str, actor: Actor
) -> Account:
    with transaction.atomic(using=_alias()):
        account = _locked(account_id)
        if account.status == AccountStatus.CLOSED:
            raise ConflictStateError("A closed account cannot be blocked or unblocked.")
        account.debit_blocked, account.credit_blocked = debit, credit
        account.version += 1
        account.save(update_fields=["debit_blocked", "credit_blocked", "version", "updated_at"])
        _history(account, account.status, reason, actor)
        _status_evidence(account, account.status, reason, actor)
    return account


def close_account(account_id: UUID, reason: str, actor: Actor) -> Account:
    with transaction.atomic(using=_alias()):
        account = _locked(account_id)
        if AccountStatus.CLOSED not in _TRANSITIONS[account.status]:
            raise ConflictStateError("Account is already closed.")
        snap = snapshot(account)
        for bal in ledger.balances_for_owner(account.id):
            if bal.held_amount or bal.pending_debit or bal.pending_credit:
                raise AccountStateInvalidError("Account has active holds or pending amounts.")
            if bal.book_balance != 0 and not snap.definition.lifecycle.allow_close_with_balance:
                raise AccountStateInvalidError(
                    f"Account cannot be closed with a non-zero {bal.purpose.lower()} book "
                    f"balance ({Money(bal.book_balance, bal.currency)})."
                )
        old = account.status
        account.status = AccountStatus.CLOSED
        account.closed_on = clock.business_date()
        account.version += 1
        account.save(update_fields=["status", "closed_on", "version", "updated_at"])
        _history(account, old, reason, actor)
        _status_evidence(account, old, reason, actor)
    return account


def _status_evidence(account: Account, old: str, reason: str, actor: Actor) -> None:
    record_event(
        operation="account.status.changed",
        resource_type="account",
        resource_id=str(account.id),
        actor=actor.id,
        actor_type=actor.type,
        payload={
            "from": old,
            "to": account.status,
            "debit_blocked": account.debit_blocked,
            "credit_blocked": account.credit_blocked,
            "reason": reason[:200],
        },
    )
    emit(
        "account.status.changed",
        aggregate_type="account",
        aggregate_id=str(account.id),
        payload={
            "account_id": str(account.id),
            "from": old,
            "to": account.status,
            "debit_blocked": account.debit_blocked,
            "credit_blocked": account.credit_blocked,
        },
    )


def interest_bearing_accounts() -> list[UUID]:
    return list(
        Account.objects.filter(status__in=[AccountStatus.ACTIVE, AccountStatus.DORMANT])
        .exclude(interest_balance_id=None)
        .order_by("id")
        .values_list("id", flat=True)
    )
