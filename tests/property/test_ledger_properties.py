"""Ledger properties on real PostgreSQL: random posting sequences keep every entry balanced,
projections equal reconstruction from postings, value is conserved, and reversing everything
restores the starting position."""

import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from next_core.ledger import application as ledger
from next_core.ledger.domain import Direction, EntrySpec, GLType, PostingLine
from next_core.ledger.integrity import verify_ledger
from next_core.ledger.models import JournalEntry
from next_core.platform.errors import InsufficientFundsError
from next_core.platform.money import Money
from next_core.tenancy.context import TenantContext
from tests.conftest import TENANT_DBS

pytestmark = [pytest.mark.integration, pytest.mark.django_db(databases=TENANT_DBS)]

moves = st.lists(
    st.tuples(st.integers(0, 3), st.integers(0, 3), st.integers(1, 50_000)), min_size=1, max_size=25
)


@settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(moves=moves, enforce=st.booleans())
def test_random_postings_conserve_and_reconstruct(
    alpha: TenantContext, moves: list[tuple[int, int, int]], enforce: bool
) -> None:
    ledger.ensure_gl_accounts(
        [
            ledger.GLSeed("1010", "Cash", GLType.ASSET),
            ledger.GLSeed("2110", "Deposits", GLType.LIABILITY),
        ]
    )
    vault = ledger.internal_balance("1010", "EUR")
    accs = [
        ledger.open_balance(
            gl_code="2110", currency="EUR", owner_id=uuid.uuid4(), funds_enforced=enforce
        )
        for _ in range(4)
    ]
    for acc in accs:  # fund each account with 1000.00
        m = Money(100_000, "EUR")
        ledger.post(
            ledger.PostingRequest(
                "PROP",
                uuid.uuid4(),
                (
                    EntrySpec(
                        "FUND",
                        (
                            PostingLine(vault.id, Direction.DEBIT, m),
                            PostingLine(acc.id, Direction.CREDIT, m),
                        ),
                    ),
                ),
            )
        )
    posted: list[uuid.UUID] = []
    for src, dst, amount in moves:
        if src == dst:
            continue
        m = Money(amount, "EUR")
        spec = EntrySpec(
            "MOVE",
            (
                PostingLine(accs[src].id, Direction.DEBIT, m),
                PostingLine(accs[dst].id, Direction.CREDIT, m),
            ),
        )
        try:
            result = ledger.post(ledger.PostingRequest("PROP", uuid.uuid4(), (spec,)))
            posted.append(result.entries[0].id)
        except InsufficientFundsError:
            assert enforce
    books = [ledger.get_balance(a.id).book_balance for a in accs]
    assert sum(books) == 400_000  # conservation among customer balances
    if enforce:
        assert min(books) >= 0
    assert verify_ledger().ok

    # Reversal symmetry: reversing every move restores the funded position exactly.
    if posted:
        ledger.post(
            ledger.PostingRequest(
                "PROP-REV", uuid.uuid4(), ledger.reversal_specs(posted), allow_overdraw=True
            )
        )
    assert [ledger.get_balance(a.id).book_balance for a in accs] == [100_000] * 4
    assert JournalEntry.objects.filter(reversal_of__id__in=posted).count() == len(posted)
    assert verify_ledger().ok
