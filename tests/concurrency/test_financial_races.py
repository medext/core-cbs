"""Hostile concurrency suite (docs/architecture/idempotency-concurrency.md) on real
PostgreSQL. Postcondition everywhere: money conservation + reconstruction == projection."""

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.db import transaction

from next_core.accounts import application as accounts
from next_core.accounts.models import Account
from next_core.control_plane.models import Tenant
from next_core.ledger import application as ledger
from next_core.ledger.integrity import verify_ledger
from next_core.ledger.models import JournalEntry
from next_core.platform.errors import (
    AccountStateInvalidError,
    ConflictStateError,
    DomainError,
    IdempotencyConflictError,
    InsufficientFundsError,
    LimitExceededError,
)
from next_core.platform.money import Money
from next_core.tenancy.context import TenantContext, tenant_context
from next_core.transactions import application as txns
from next_core.transactions.models import BusinessTransaction, TxnState
from tests import factories as f
from tests.concurrency.harness import run_parallel
from tests.conftest import TENANT_DBS, ctx_for

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(databases=TENANT_DBS, transaction=True),
]
BRANCH = txns.CommonFields(channel="BRANCH")  # fee-free channel for transfers


@pytest.fixture()
def ctx(tenants: dict[str, Tenant]) -> Iterator[TenantContext]:
    c = ctx_for(tenants["alpha"])
    with tenant_context(c):
        yield c


def atomic(fn: Callable[[], Any]) -> Callable[[], Any]:
    def run() -> Any:
        with transaction.atomic(using="tenant_alpha"):
            return fn()

    return run


def book(acc: Account) -> int:
    return ledger.get_balance(acc.principal_balance_id).book_balance


def held(acc: Account) -> int:
    return ledger.get_balance(acc.principal_balance_id).held_amount


def _assert_integrity() -> None:
    run = verify_ledger()
    assert run.ok, run.findings


def test_double_spend_never_overdraws(ctx: TenantContext) -> None:
    products = f.bootstrap()
    src, dst = f.account(products), f.account(products)
    f.deposit(src, "1000.00")
    fns = [
        atomic(lambda: txns.transfer(src.id, dst.id, Money(20_000, "MRU"), BRANCH, f.TELLER))
        for _ in range(10)
    ]
    results = run_parallel(ctx, fns)
    ok = [r for r in results if isinstance(r, BusinessTransaction)]
    rejected = [r for r in results if isinstance(r, InsufficientFundsError)]
    assert len(ok) == 5 and len(rejected) == 5, results
    assert book(src) == 0 and book(dst) == 100_000
    _assert_integrity()


def test_concurrent_duplicate_requests_post_once(ctx: TenantContext) -> None:
    products = f.bootstrap()
    src, dst = f.account(products), f.account(products)
    f.deposit(src, "1000.00")
    payload = {"source": str(src.id), "target": str(dst.id), "amount": "10.00"}
    idem = txns.Idempotency("transfer", "client-1", "same-key")

    def call() -> txns.Outcome:
        return txns.execute_idempotent(
            idem,
            payload,
            lambda: txns.transfer(src.id, dst.id, Money(1_000, "MRU"), BRANCH, f.TELLER),
            lambda exc: None,
        )

    results = run_parallel(ctx, [call] * 8)
    assert all(isinstance(r, txns.Outcome) for r in results), results
    assert len({r.body["id"] for r in results}) == 1
    assert sum(not r.replayed for r in results) == 1
    assert book(dst) == 1_000
    assert BusinessTransaction.objects.filter(state=TxnState.POSTED, type="TRANSFER").count() == 1
    _assert_integrity()


def test_same_key_different_payload_executes_once(ctx: TenantContext) -> None:
    products = f.bootstrap()
    src, dst = f.account(products), f.account(products)
    f.deposit(src, "1000.00")
    idem = txns.Idempotency("transfer", "client-1", "k-1")

    def call(minor: int) -> Callable[[], Any]:
        return lambda: txns.execute_idempotent(
            idem,
            {"amount": minor},
            lambda: txns.transfer(src.id, dst.id, Money(minor, "MRU"), BRANCH, f.TELLER),
            lambda exc: None,
        )

    results = run_parallel(ctx, [call(100), call(200)] * 3)
    executed = [r for r in results if isinstance(r, txns.Outcome) and not r.replayed]
    conflicts = [r for r in results if isinstance(r, IdempotencyConflictError)]
    assert len(executed) == 1 and len(conflicts) >= 2, results
    assert book(dst) in (100, 200)
    _assert_integrity()


def test_capture_vs_release_race(ctx: TenantContext) -> None:
    products = f.bootstrap()
    src, dst = f.account(products), f.account(products)
    f.deposit(src, "100.00")
    with transaction.atomic(using="tenant_alpha"):
        hold_txn = txns.place_hold(src.id, Money(5_000, "MRU"), 3600, BRANCH, f.TELLER)
    hold_id = hold_txn.hold.id
    results = run_parallel(
        ctx,
        [
            atomic(lambda: txns.capture_hold(hold_id, None, dst.id, f.TELLER)),
            atomic(lambda: txns.release_hold(hold_id, f.TELLER)),
        ]
        * 3,
    )
    winners = [r for r in results if isinstance(r, BusinessTransaction)]
    assert len(winners) == 1 and all(
        isinstance(r, ConflictStateError) for r in results if r not in winners
    )
    assert held(src) == 0
    assert book(src) + book(dst) == 10_000
    _assert_integrity()


def test_concurrent_reversals_of_one_transaction(ctx: TenantContext) -> None:
    products = f.bootstrap()
    src, dst = f.account(products), f.account(products)
    f.deposit(src, "100.00")
    with transaction.atomic(using="tenant_alpha"):
        t = txns.transfer(src.id, dst.id, Money(4_000, "MRU"), BRANCH, f.TELLER)
    results = run_parallel(ctx, [atomic(lambda: txns.reverse(t.id, "dup", f.SUPERVISOR))] * 6)
    assert sum(isinstance(r, BusinessTransaction) for r in results) == 1, results
    assert all(isinstance(r, BusinessTransaction | ConflictStateError) for r in results)
    assert JournalEntry.objects.exclude(reversal_of=None).count() == 1
    assert book(src) == 10_000 and book(dst) == 0
    _assert_integrity()


def test_opposite_direction_transfer_storm_has_no_deadlock(ctx: TenantContext) -> None:
    products = f.bootstrap()
    a, b = f.account(products), f.account(products)
    f.deposit(a, "1000.00")
    f.deposit(b, "1000.00")
    ab = atomic(lambda: txns.transfer(a.id, b.id, Money(100, "MRU"), BRANCH, f.TELLER))
    ba = atomic(lambda: txns.transfer(b.id, a.id, Money(100, "MRU"), BRANCH, f.TELLER))
    results = run_parallel(ctx, [ab, ba] * 12)
    assert all(isinstance(r, BusinessTransaction) for r in results), results
    assert book(a) == book(b) == 100_000
    _assert_integrity()


def test_limit_count_cannot_be_overconsumed(ctx: TenantContext) -> None:
    products = f.bootstrap()
    s = f.account(products, "SAVINGS")  # MONTHLY_WITHDRAWALS max_count = 4
    f.deposit(s, "10000.00")
    results = run_parallel(
        ctx, [atomic(lambda: txns.withdrawal(s.id, Money(100, "MRU"), BRANCH, f.TELLER))] * 10
    )
    assert sum(isinstance(r, BusinessTransaction) for r in results) == 4, results
    assert sum(isinstance(r, LimitExceededError) for r in results) == 6
    _assert_integrity()


def test_closure_vs_incoming_deposit(ctx: TenantContext) -> None:
    products = f.bootstrap()
    acc = f.account(products)
    results = run_parallel(
        ctx,
        [
            lambda: accounts.close_account(acc.id, "race", f.TELLER),
            atomic(lambda: txns.deposit(acc.id, Money(100, "MRU"), BRANCH, f.TELLER)),
        ],
    )
    closed, deposited = results
    acc.refresh_from_db()
    if isinstance(deposited, BusinessTransaction):
        # deposit won the account lock → closure must have refused a non-zero balance
        assert isinstance(closed, AccountStateInvalidError) and acc.status == "ACTIVE"
    else:
        assert isinstance(deposited, AccountStateInvalidError) and acc.status == "CLOSED"
        assert book(acc) == 0
    assert all(isinstance(r, Account | BusinessTransaction | DomainError) for r in results)
    _assert_integrity()


def test_simultaneous_holds_never_exceed_available(ctx: TenantContext) -> None:
    products = f.bootstrap()
    acc = f.account(products)
    f.deposit(acc, "100.00")
    results = run_parallel(
        ctx,
        [atomic(lambda: txns.place_hold(acc.id, Money(3_000, "MRU"), 3600, BRANCH, f.TELLER))] * 8,
    )
    assert sum(isinstance(r, BusinessTransaction) for r in results) == 3, results
    assert held(acc) == 9_000 and txns.reconcile_holds() == []
    _assert_integrity()


def test_expiry_sweep_vs_capture(ctx: TenantContext, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import timedelta

    from next_core.platform import clock

    products = f.bootstrap()
    src, dst = f.account(products), f.account(products)
    f.deposit(src, "100.00")
    with transaction.atomic(using="tenant_alpha"):
        hold_txn = txns.place_hold(src.id, Money(5_000, "MRU"), 60, BRANCH, f.TELLER)
    hold_id = hold_txn.hold.id
    real_now = clock.now
    monkeypatch.setattr(clock, "now", lambda: real_now() + timedelta(seconds=120))
    results = run_parallel(
        ctx,
        [
            lambda: txns.expire_holds(f.TELLER),
            atomic(lambda: txns.capture_hold(hold_id, None, dst.id, f.TELLER)),
        ],
    )
    # Expired by the clock: capture must refuse; the sweep converts the hold exactly once.
    assert isinstance(results[1], ConflictStateError), results
    assert held(src) == 0 and book(src) == 10_000 and book(dst) == 0
    _assert_integrity()


def test_deadlock_is_retried_transparently(ctx: TenantContext) -> None:
    """Force a real PostgreSQL deadlock inside two idempotent executions (opposite lock
    order + barrier); the loser must be retried by execute_idempotent and both succeed."""
    import threading

    from next_core.accounts.models import Account as AccountModel

    products = f.bootstrap()
    a, b = f.account(products), f.account(products)
    f.deposit(a, "100.00")
    f.deposit(b, "100.00")
    barrier = threading.Barrier(2)
    first_attempt = {"ab": True, "ba": True}

    def work(order: str, first: Account, second: Account) -> Callable[[], Any]:
        def run() -> BusinessTransaction:
            AccountModel.objects.select_for_update().get(id=first.id)
            if first_attempt[order]:
                first_attempt[order] = False
                barrier.wait(timeout=30)
            AccountModel.objects.select_for_update().get(id=second.id)
            return txns.transfer(first.id, second.id, Money(100, "MRU"), BRANCH, f.TELLER)

        return run

    def call(order: str, first: Account, second: Account) -> Callable[[], Any]:
        return lambda: txns.execute_idempotent(
            txns.Idempotency("transfer", "c", order),
            {"o": order},
            work(order, first, second),
            lambda exc: None,
        )

    results = run_parallel(ctx, [call("ab", a, b), call("ba", b, a)])
    assert all(isinstance(r, txns.Outcome) and r.status == 201 for r in results), results
    assert book(a) == book(b) == 10_000
    _assert_integrity()


def test_duplicate_requests_replay_identical_status_and_body(ctx: TenantContext) -> None:
    products = f.bootstrap()
    acc = f.account(products)
    idem = txns.Idempotency("deposit", "client-9", "dup-body")

    def call() -> txns.Outcome:
        return txns.execute_idempotent(
            idem,
            {"a": 1},
            lambda: txns.deposit(acc.id, Money(500, "MRU"), BRANCH, f.TELLER),
            lambda exc: None,
        )

    results = run_parallel(ctx, [call] * 6)
    assert len({(r.status, json.dumps(r.body, sort_keys=True)) for r in results}) == 1
    assert book(acc) == 500


def test_retryable_errors_are_not_stored_and_same_key_retry_succeeds(ctx: TenantContext) -> None:
    """Concurrency review N1: a retryable DomainError must not burn the idempotency key."""
    from next_core.platform.errors import RequestInProgressError
    from next_core.transactions.models import IdempotencyRecord

    products = f.bootstrap()
    acc = f.account(products)
    idem = txns.Idempotency("deposit", "client-r", "retry-key")
    attempts = {"n": 0}

    def flaky() -> BusinessTransaction:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RequestInProgressError("transient")
        return txns.deposit(acc.id, Money(100, "MRU"), BRANCH, f.TELLER)

    with pytest.raises(RequestInProgressError):
        txns.execute_idempotent(idem, {"x": 1}, flaky, lambda exc: None)
    assert not IdempotencyRecord.objects.filter(key="retry-key").exists()
    assert not BusinessTransaction.objects.filter(state="REJECTED").exists()
    out = txns.execute_idempotent(idem, {"x": 1}, flaky, lambda exc: None)
    assert out.status == 201 and not out.replayed and book(acc) == 100
