"""Business flows through the application services on real PostgreSQL."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.db import transaction

from next_core.accounts import application as accounts
from next_core.accounts.models import Account
from next_core.ledger import application as ledger
from next_core.ledger.integrity import verify_ledger
from next_core.platform import clock
from next_core.platform.errors import (
    AccountStateInvalidError,
    AmountExceedsOutstandingError,
    CreditLimitExceededError,
    InsufficientFundsError,
    KycLevelInsufficientError,
    LimitExceededError,
    MakerCheckerViolationError,
    OperationNotAllowedError,
    ProductRuleViolationError,
    ValidationFailedError,
)
from next_core.platform.money import Money
from next_core.tenancy.context import TenantContext
from next_core.transactions import application as txns
from next_core.transactions.models import TxnState
from tests import factories as f
from tests.conftest import TENANT_DBS

pytestmark = [pytest.mark.integration, pytest.mark.django_db(databases=TENANT_DBS)]
C = txns.CommonFields


def book(acc: Account) -> str:
    b = ledger.get_balance(acc.principal_balance_id)
    return Money(b.book_balance, b.currency).to_wire()


def avail(acc: Account) -> str:
    b = ledger.get_balance(acc.principal_balance_id)
    return Money(b.available_balance, b.currency).to_wire()


def atomic(fn: Callable[..., Any], *a: Any, **kw: Any) -> Any:
    with transaction.atomic(using="tenant_alpha"):
        return fn(*a, **kw)


def test_current_account_full_cycle(alpha: TenantContext) -> None:
    products = f.bootstrap()
    a, b = f.account(products), f.account(products)
    f.deposit(a, "1000.00")
    assert book(a) == "1000.00"

    # transfer via API channel: 0.5% fee (min 4.00 MRU) + 16% tax charged to the sender
    t = atomic(txns.transfer, a.id, b.id, f.money("200.00"), C(channel="API"), f.TELLER)
    assert t.state == TxnState.POSTED
    assert t.fees[0]["amount"] == "4.00" and t.fees[0]["tax"] == "0.64"
    assert book(a) == "795.36" and book(b) == "200.00"

    # withdrawal: flat 20.00 MRU + 3.20 tax
    atomic(txns.withdrawal, a.id, f.money("100.00"), C(), f.TELLER)
    assert book(a) == "672.16"

    with pytest.raises(InsufficientFundsError):
        atomic(txns.transfer, a.id, b.id, f.money("700.00"), C(channel="BRANCH"), f.TELLER)

    # hold then partial capture
    h = atomic(txns.place_hold, a.id, f.money("100.00"), 3600, C(), f.TELLER)
    assert avail(a) == "572.16"
    hold_id = h.hold.id
    cap = atomic(txns.capture_hold, hold_id, f.money("60.00"), b.id, f.TELLER)
    assert cap.state == TxnState.POSTED
    assert book(a) == "612.16" and avail(a) == "612.16"

    # reversal restores the economic position (principal + fees)
    rev = atomic(txns.reverse, t.id, "customer dispute", f.SUPERVISOR)
    assert rev.state == TxnState.POSTED
    assert book(a) == "816.80"  # 612.16 + 200.00 + 4.64 fees
    assert verify_ledger().ok


def test_overdraft_override_within_product_bounds(alpha: TenantContext) -> None:
    products = f.bootstrap()
    a = f.account(products, overrides={"overdraft_limit": "500.00"})
    b = f.account(products)
    atomic(txns.transfer, a.id, b.id, f.money("400.00"), C(channel="BRANCH"), f.TELLER)
    assert book(a) == "-400.00" and avail(a) == "100.00"
    with pytest.raises(InsufficientFundsError):
        atomic(txns.transfer, a.id, b.id, f.money("100.01"), C(channel="BRANCH"), f.TELLER)


def test_daily_limit(alpha: TenantContext) -> None:
    products = f.bootstrap()
    a, b = f.account(products, "CURRENT", "EUR"), f.account(products, "CURRENT", "EUR")
    f.deposit(a, "20000.00")
    atomic(txns.transfer, a.id, b.id, f.money("9000.00", "EUR"), C(channel="BRANCH"), f.TELLER)
    with pytest.raises(LimitExceededError):
        atomic(txns.withdrawal, a.id, f.money("1000.01", "EUR"), C(), f.TELLER)


def test_term_deposit_rules_and_interest(
    alpha: TenantContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    products = f.bootstrap()
    td = f.account(products, "TERM_DEPOSIT", overrides={"term_days": 30})
    with pytest.raises(ProductRuleViolationError):  # below min opening 20000.00 MRU
        f.deposit(td, "100.00")
    f.deposit(td, "36500.00")
    with pytest.raises(ProductRuleViolationError):  # single funding
        f.deposit(td, "1.00")
    with pytest.raises(ProductRuleViolationError):  # locked until maturity
        atomic(txns.withdrawal, td.id, f.money("1.00"), C(), f.TELLER)
    today = clock.business_date()
    assert txns.accrue_interest_for(td.id, today, f.TELLER) == 1  # 36500 * 5% / 365 = 5.00
    assert txns.accrue_interest_for(td.id, today, f.TELLER) == 0  # idempotent
    assert td.interest_balance_id is not None and td.maturity_date is not None
    accrued = ledger.get_balance(td.interest_balance_id)
    assert accrued.book_balance == 500
    maturity = td.maturity_date
    monkeypatch.setattr(clock, "business_date", lambda: maturity)
    # At maturity, capitalization waits until accrual has run through maturity - 1 (never partial)
    assert txns.capitalize_interest_for(td.id, maturity, f.TELLER) == 0
    monkeypatch.setattr(clock, "business_date", lambda: today)
    with pytest.raises(ValidationFailedError):  # ledger review B1: never for a future date
        txns.capitalize_interest_for(td.id, maturity, f.TELLER)
    with pytest.raises(ValidationFailedError):
        txns.accrue_interest_for(td.id, today + timedelta(days=1), f.TELLER)
    # Time travel to maturity: catch-up accrues each remaining day once, on the value-dated
    # balance, and stops the day before maturity; then capitalization at maturity.
    monkeypatch.setattr(clock, "business_date", lambda: maturity)
    assert txns.accrue_interest_for(td.id, maturity, f.TELLER) == 29
    assert ledger.get_balance(td.interest_balance_id).book_balance == 500 * 30
    assert txns.capitalize_interest_for(td.id, maturity, f.TELLER)
    assert book(td) == "36650.00"
    assert txns.accrue_interest_for(td.id, maturity, f.TELLER) == 0
    assert verify_ledger().ok


def test_wallet_kyc_tier_cap_and_tiered_fee(alpha: TenantContext) -> None:
    products = f.bootstrap()
    w0 = f.account(products, "WALLET", owner=f.party(kyc_level=0))
    with pytest.raises(ProductRuleViolationError):
        f.deposit(w0, "8000.01")
    f.deposit(w0, "8000.00")
    w1 = f.account(products, "WALLET")
    t = atomic(txns.transfer, w0.id, w1.id, f.money("1000.00"), C(), f.TELLER)
    assert t.fees[0]["amount"] == "10.00"  # 1% tier
    with pytest.raises(OperationNotAllowedError):
        atomic(txns.disburse, w0.id, w1.id, f.money("1.00"), C(), f.TELLER)


def test_kyc_gate_on_opening(alpha: TenantContext) -> None:
    products = f.bootstrap()
    with pytest.raises(KycLevelInsufficientError):
        f.account(products, "PERSONAL_LOAN", owner=f.party(kyc_level=1))


def test_loan_disbursement_repayment_and_interest(alpha: TenantContext) -> None:
    products = f.bootstrap()
    owner = f.party(kyc_level=2)
    loan = f.account(products, "PERSONAL_LOAN", owner=owner)  # limit 40000.00 MRU
    cur = f.account(products, "CURRENT", owner=owner)
    d = atomic(txns.disburse, loan.id, cur.id, f.money("10000.00"), C(), f.TELLER)
    assert d.fees[0]["amount"] == "100.00"  # 1% origination, charged to the loan
    assert book(loan) == "10100.00" and book(cur) == "10000.00"
    with pytest.raises(CreditLimitExceededError):
        atomic(txns.disburse, loan.id, cur.id, f.money("29800.00"), C(), f.TELLER)
    with pytest.raises(AmountExceedsOutstandingError):
        atomic(txns.repay, cur.id, loan.id, f.money("10100.01"), C(channel="BRANCH"), f.TELLER)
    atomic(txns.repay, cur.id, loan.id, f.money("100.00"), C(channel="BRANCH"), f.TELLER)
    assert book(loan) == "10000.00"
    assert txns.accrue_interest_for(loan.id, clock.business_date(), f.TELLER) == 1
    # 10000.00 * 12% / 360 = 3.33 (half-even)
    assert loan.interest_balance_id is not None
    assert ledger.get_balance(loan.interest_balance_id).book_balance == 333
    assert verify_ledger().ok


def test_closure_rules(alpha: TenantContext) -> None:
    products = f.bootstrap()
    a, b = f.account(products), f.account(products)
    f.deposit(a, "10.00")
    with pytest.raises(AccountStateInvalidError):
        accounts.close_account(a.id, "customer request", f.TELLER)
    atomic(txns.transfer, a.id, b.id, f.money("10.00"), C(channel="BRANCH"), f.TELLER)
    closed = accounts.close_account(a.id, "customer request", f.TELLER)
    assert closed.status == "CLOSED"
    with pytest.raises(AccountStateInvalidError):
        f.deposit(a, "1.00")
    assert ledger.statement(a.principal_balance_id)[0]  # history preserved


def test_frozen_and_debit_block(alpha: TenantContext) -> None:
    products = f.bootstrap()
    a = f.account(products)
    f.deposit(a, "100.00")
    accounts.set_blocks(a.id, debit=True, credit=False, reason="court order", actor=f.TELLER)
    with pytest.raises(AccountStateInvalidError):
        atomic(txns.withdrawal, a.id, f.money("1.00"), C(), f.TELLER)
    f.deposit(a, "1.00")  # credits still allowed
    accounts.change_status(a.id, "FROZEN", "investigation", f.TELLER)
    with pytest.raises(AccountStateInvalidError):
        f.deposit(a, "1.00")


def test_initiator_cannot_reverse_own_transaction(alpha: TenantContext) -> None:
    products = f.bootstrap()
    a, b = f.account(products), f.account(products)
    f.deposit(a, "50.00")
    t = atomic(txns.transfer, a.id, b.id, f.money("10.00"), C(channel="BRANCH"), f.TELLER)
    with pytest.raises(MakerCheckerViolationError):
        atomic(txns.reverse, t.id, "self-reversal", f.TELLER)


def test_backdated_accrual_uses_value_dated_balance(
    alpha: TenantContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    products = f.bootstrap()
    s = f.account(products, "SAVINGS")
    opened = clock.business_date()
    f.deposit(s, "36500.00")
    later = opened + timedelta(days=3)
    monkeypatch.setattr(clock, "business_date", lambda: later)
    f.deposit(s, "36500.00")  # value-dated `later`: must not inflate days 0..2
    assert txns.accrue_interest_for(s.id, later, f.TELLER) == 4
    assert s.interest_balance_id is not None
    # 3 days x 3.00 on 36500 + 1 day x 6.00 on 73000
    assert ledger.get_balance(s.interest_balance_id).book_balance == 3 * 300 + 600
    assert verify_ledger().ok


def test_holds_reconcile_with_projection(alpha: TenantContext) -> None:
    products = f.bootstrap()
    a, b = f.account(products), f.account(products)
    f.deposit(a, "100.00")
    h1 = atomic(txns.place_hold, a.id, f.money("10.00"), 3600, C(), f.TELLER)
    atomic(txns.place_hold, a.id, f.money("20.00"), 3600, C(), f.TELLER)
    atomic(txns.capture_hold, h1.hold.id, f.money("5.00"), b.id, f.TELLER)
    assert txns.reconcile_holds() == []
    assert ledger.get_balance(a.principal_balance_id).held_amount == 2000


def test_monthly_capitalization_catches_up_in_order_and_never_early(
    alpha: TenantContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ledger review condition 1: missed 1sts are caught up in order; each capitalization
    only moves interest accrued with value_date < the capitalization date."""
    from datetime import date

    products = f.bootstrap()
    monkeypatch.setattr(clock, "business_date", lambda: date(2026, 11, 25))
    s = f.account(products, "SAVINGS")
    f.deposit(s, "36500.00")
    monkeypatch.setattr(clock, "business_date", lambda: date(2027, 1, 15))
    assert txns.capitalize_interest_for(s.id, date(2027, 1, 15), f.TELLER) == 0  # accrue first
    # Accrual catch-up applies the due capitalizations (12-01, 01-01) in date order.
    assert txns.accrue_interest_for(s.id, date(2027, 1, 15), f.TELLER) == 52
    # 12-01: 6 days (11-25..11-30) x 3.00; 01-01: 31 days x 3.00 on 36518.00 (3.0015 → 3.00)
    assert book(s) == "36611.00"
    assert txns.capitalize_interest_for(s.id, date(2027, 1, 15), f.TELLER) == 0  # resumable
    assert s.interest_balance_id is not None
    # 14 days of January (01-01..01-14 on 36611.00 → 3.01) + 01-15 remain accrued, unpaid
    remaining = ledger.get_balance(s.interest_balance_id).book_balance
    assert remaining == 15 * 301  # compounding: January accrues on 36611.00
    assert verify_ledger().ok
