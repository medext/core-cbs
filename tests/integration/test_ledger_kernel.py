"""Ledger kernel on real PostgreSQL: posting service + database enforcement (migration 0002).

Each DB-trigger test writes *around* the posting service on purpose, proving that the
database refuses what application code must never do (invariants 1, 5, 8, 16, 18, 24).
"""

import uuid
from typing import Any

import pytest
from django.db import DatabaseError, connections, transaction

from next_core.ledger import application as ledger
from next_core.ledger.domain import Direction, EntrySpec, GLType, HoldChange, PostingLine
from next_core.ledger.integrity import verify_ledger
from next_core.ledger.models import JournalEntry, LedgerBalance, Posting
from next_core.platform.errors import (
    ConflictStateError,
    CurrencyMismatchError,
    InsufficientFundsError,
    UnbalancedEntryError,
)
from next_core.platform.money import Money
from next_core.platform.outbox.models import OutboxEvent
from next_core.tenancy.context import TenantContext
from tests.conftest import TENANT_DBS

pytestmark = [pytest.mark.integration, pytest.mark.django_db(databases=TENANT_DBS)]

SEEDS = [
    ledger.GLSeed("1010", "Vault cash", GLType.ASSET),
    ledger.GLSeed("2110", "Customer deposits", GLType.LIABILITY),
    ledger.GLSeed("4100", "Fee income", GLType.INCOME),
]


def _setup(funds: bool = True) -> tuple[ledger.BalanceView, ledger.BalanceView, ledger.BalanceView]:
    ledger.ensure_gl_accounts(SEEDS)
    vault = ledger.internal_balance("1010", "MRU")
    a = ledger.open_balance(
        gl_code="2110", currency="MRU", owner_id=uuid.uuid4(), funds_enforced=funds
    )
    b = ledger.open_balance(
        gl_code="2110", currency="MRU", owner_id=uuid.uuid4(), funds_enforced=funds
    )
    return vault, a, b


def _move(src: uuid.UUID, dst: uuid.UUID, minor: int, purpose: str = "PRINCIPAL") -> EntrySpec:
    m = Money(minor, "MRU")
    return EntrySpec(
        purpose=purpose,
        lines=(PostingLine(src, Direction.DEBIT, m), PostingLine(dst, Direction.CREDIT, m)),
    )


def _deposit(
    vault: ledger.BalanceView, acc: ledger.BalanceView, minor: int
) -> ledger.PostingResult:
    return ledger.post(
        ledger.PostingRequest("TEST", uuid.uuid4(), (_move(vault.id, acc.id, minor),))
    )


def _raw(alias: str, sql: str, params: list[Any] | None = None, writer: bool = False) -> None:
    with transaction.atomic(using=alias), connections[alias].cursor() as cur:
        if writer:
            cur.execute("SELECT set_config('next_core.ledger_writer','on',true)")
        cur.execute(sql, params or [])
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_deposit_updates_projections_and_emits_event(alpha: TenantContext) -> None:
    vault, a, _ = _setup()
    result = _deposit(vault, a, 10_000)
    assert result.balances[a.id].book_balance == 10_000
    assert result.balances[a.id].available_balance == 10_000
    assert result.balances[vault.id].book_balance == 10_000  # asset up
    assert OutboxEvent.objects.filter(event_type="journal_entry.posted").count() == 1
    assert verify_ledger().ok


def test_unbalanced_entry_rejected_by_domain(alpha: TenantContext) -> None:
    vault, a, _ = _setup()
    bad = EntrySpec(
        "X",
        (
            PostingLine(vault.id, Direction.DEBIT, Money(100, "MRU")),
            PostingLine(a.id, Direction.CREDIT, Money(90, "MRU")),
        ),
    )
    with pytest.raises(UnbalancedEntryError):
        ledger.post(ledger.PostingRequest("TEST", uuid.uuid4(), (bad,)))


def test_insufficient_funds_rejected_and_nothing_persisted(alpha: TenantContext) -> None:
    vault, a, b = _setup()
    _deposit(vault, a, 5_000)
    with pytest.raises(InsufficientFundsError):
        ledger.post(ledger.PostingRequest("TEST", uuid.uuid4(), (_move(a.id, b.id, 5_001),)))
    assert ledger.get_balance(a.id).book_balance == 5_000
    assert ledger.get_balance(b.id).book_balance == 0
    assert JournalEntry.objects.count() == 1


def test_holds_reduce_available_and_are_funds_checked(alpha: TenantContext) -> None:
    vault, a, _ = _setup()
    _deposit(vault, a, 10_000)
    ledger.post(
        ledger.PostingRequest("HOLD", uuid.uuid4(), hold_changes=(HoldChange(a.id, 3_000, "MRU"),))
    )
    view = ledger.get_balance(a.id)
    assert (view.book_balance, view.held_amount, view.available_balance) == (10_000, 3_000, 7_000)
    with pytest.raises(InsufficientFundsError):
        ledger.post(
            ledger.PostingRequest(
                "HOLD", uuid.uuid4(), hold_changes=(HoldChange(a.id, 7_001, "MRU"),)
            )
        )


def test_currency_mismatch_rejected(alpha: TenantContext) -> None:
    vault, _, _ = _setup()
    eur = ledger.open_balance(gl_code="2110", currency="EUR", owner_id=uuid.uuid4())
    m = Money(100, "MRU")
    spec = EntrySpec(
        "X", (PostingLine(vault.id, Direction.DEBIT, m), PostingLine(eur.id, Direction.CREDIT, m))
    )
    with pytest.raises(CurrencyMismatchError):
        ledger.post(ledger.PostingRequest("TEST", uuid.uuid4(), (spec,)))


def test_same_source_and_purpose_cannot_post_twice(alpha: TenantContext) -> None:
    vault, a, _ = _setup()
    source = uuid.uuid4()
    ledger.post(ledger.PostingRequest("TEST", source, (_move(vault.id, a.id, 100),)))
    with pytest.raises(ConflictStateError):
        ledger.post(ledger.PostingRequest("TEST", source, (_move(vault.id, a.id, 100),)))
    assert ledger.get_balance(a.id).book_balance == 100


def test_reversal_restores_position_and_is_single(alpha: TenantContext) -> None:
    vault, a, b = _setup()
    _deposit(vault, a, 1_000)
    original = ledger.post(ledger.PostingRequest("TEST", uuid.uuid4(), (_move(a.id, b.id, 400),)))
    entry_id = original.entries[0].id
    specs = ledger.reversal_specs([entry_id])
    ledger.post(ledger.PostingRequest("REV", uuid.uuid4(), specs, allow_overdraw=True))
    assert ledger.get_balance(a.id).book_balance == 1_000
    assert ledger.get_balance(b.id).book_balance == 0
    with pytest.raises(ConflictStateError):
        ledger.reversal_specs([entry_id])
    # DB backstop: a second mirror entry pointing at the same original is refused.
    with pytest.raises(ConflictStateError):
        ledger.post(ledger.PostingRequest("REV", uuid.uuid4(), specs, allow_overdraw=True))
    assert verify_ledger().ok


# --- database enforcement (writes around the service) -------------------------------------


def test_db_refuses_update_and_delete_of_postings_and_entries(alpha: TenantContext) -> None:
    vault, a, _ = _setup()
    _deposit(vault, a, 100)
    for sql in (
        "UPDATE ledger_posting SET amount = amount + 1",
        "DELETE FROM ledger_posting",
        "UPDATE ledger_journal_entry SET description = 'tampered'",
        "DELETE FROM ledger_journal_entry",
    ):
        with pytest.raises(DatabaseError, match="append-only"):
            _raw(alpha.db_alias, sql, writer=True)


def test_db_refuses_insert_outside_posting_service(alpha: TenantContext) -> None:
    _setup()
    with pytest.raises(DatabaseError, match="posting service"):
        _raw(
            alpha.db_alias,
            "INSERT INTO ledger_journal_entry (id, tenant_id, source_type, source_id, purpose, "
            "business_date, value_date, posted_at, description, metadata) VALUES "
            "(gen_random_uuid(), %s, 'X', gen_random_uuid(), 'X', now(), now(), now(), '', '{}')",
            [str(alpha.tenant_id)],
        )


def test_db_refuses_direct_balance_overwrite(alpha: TenantContext) -> None:
    _setup()
    with pytest.raises(DatabaseError, match="posting service"):
        _raw(alpha.db_alias, "UPDATE ledger_balance SET held_amount = 5")
    with pytest.raises(DatabaseError, match="cannot be deleted"):
        _raw(alpha.db_alias, "DELETE FROM ledger_balance", writer=True)
    with pytest.raises(DatabaseError, match="version"):
        _raw(alpha.db_alias, "UPDATE ledger_balance SET pending_credit = 1", writer=True)


def test_db_refuses_unbalanced_entry_at_commit(alpha: TenantContext) -> None:
    vault, a, _ = _setup()
    entry_id = uuid.uuid4()
    with (
        pytest.raises(DatabaseError, match=r"unbalanced|at least 2"),
        transaction.atomic(using=alpha.db_alias),
        connections[alpha.db_alias].cursor() as cur,
    ):
        cur.execute("SELECT set_config('next_core.ledger_writer','on',true)")
        cur.execute(
            "INSERT INTO ledger_journal_entry (id, tenant_id, source_type, source_id, purpose,"
            " business_date, value_date, posted_at, description, metadata) VALUES "
            "(%s, %s, 'X', gen_random_uuid(), 'X', now(), now(), now(), '', '{}')",
            [str(entry_id), str(alpha.tenant_id)],
        )
        for line, (bid, direction, amount) in enumerate(
            [(vault.id, "DEBIT", 100), (a.id, "CREDIT", 99)], start=1
        ):
            cur.execute(
                "INSERT INTO ledger_posting (tenant_id, entry_id, balance_id, line_no, "
                "direction, amount, currency) VALUES (%s, %s, %s, %s, %s, %s, 'MRU')",
                [str(alpha.tenant_id), str(entry_id), str(bid), line, direction, amount],
            )
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_db_refuses_posting_currency_different_from_balance(alpha: TenantContext) -> None:
    vault, _, _ = _setup()
    with (
        pytest.raises(DatabaseError, match="currency"),
        transaction.atomic(using=alpha.db_alias),
        connections[alpha.db_alias].cursor() as cur,
    ):
        cur.execute("SELECT set_config('next_core.ledger_writer','on',true)")
        eid = uuid.uuid4()
        cur.execute(
            "INSERT INTO ledger_journal_entry (id, tenant_id, source_type, source_id, purpose,"
            " business_date, value_date, posted_at, description, metadata) VALUES "
            "(%s, %s, 'X', gen_random_uuid(), 'X', now(), now(), now(), '', '{}')",
            [str(eid), str(alpha.tenant_id)],
        )
        cur.execute(
            "INSERT INTO ledger_posting (tenant_id, entry_id, balance_id, line_no, direction,"
            " amount, currency) VALUES (%s, %s, %s, 1, 'DEBIT', 5, 'EUR')",
            [str(alpha.tenant_id), str(eid), str(vault.id)],
        )


def test_db_funds_floor_backstop(alpha: TenantContext) -> None:
    vault, a, _ = _setup()
    _deposit(vault, a, 100)
    with pytest.raises(DatabaseError, match="funds floor"):
        _raw(
            alpha.db_alias,
            "UPDATE ledger_balance SET held_amount = 101, version = version + 1 WHERE id = %s",
            [str(a.id)],
            writer=True,
        )


def test_db_refuses_balance_born_with_value(alpha: TenantContext) -> None:
    _setup()
    gl = ledger.gl_account("2110")
    with pytest.raises(DatabaseError, match="created empty"):
        _raw(
            alpha.db_alias,
            "INSERT INTO ledger_balance (id, tenant_id, gl_account_id, currency, normal_side, "
            "owner_type, owner_id, purpose, debit_total, credit_total, book_balance, held_amount,"
            " pending_debit, pending_credit, overdraft_limit, funds_enforced, version, "
            "last_entry_seq, created_at, updated_at) VALUES (gen_random_uuid(), %s, %s, 'MRU', "
            "'CREDIT', 'ACCOUNT', gen_random_uuid(), 'PRINCIPAL', 0, 500, 500, 0, 0, 0, 0, false,"
            " 0, 0, now(), now())",
            [str(alpha.tenant_id), str(gl.id)],
        )


def test_integrity_detects_projection_tampering(alpha: TenantContext) -> None:
    vault, a, _ = _setup()
    _deposit(vault, a, 100)
    # Privileged tamper that respects every trigger rule except truth (monotonic totals).
    _raw(
        alpha.db_alias,
        "UPDATE ledger_balance SET credit_total = credit_total + 50, book_balance = book_balance"
        " + 50, version = version + 1 WHERE id = %s",
        [str(a.id)],
        writer=True,
    )
    run = verify_ledger()
    assert not run.ok
    assert run.findings[0]["kind"] == "PROJECTION_MISMATCH"
    assert Posting.objects.count() == 2
    assert LedgerBalance.objects.count() == 3
