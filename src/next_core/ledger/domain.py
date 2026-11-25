"""Ledger domain — pure rules, no Django imports.

Double-entry semantics (docs/accounting/accounting-model.md): every account type has a
fixed normal side; a posting on the normal side increases the book balance.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID

from next_core.platform.errors import UnbalancedEntryError, ValidationFailedError
from next_core.platform.money import Money


class Direction(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class GLType(StrEnum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


NORMAL_SIDE: dict[GLType, Direction] = {
    GLType.ASSET: Direction.DEBIT,
    GLType.EXPENSE: Direction.DEBIT,
    GLType.LIABILITY: Direction.CREDIT,
    GLType.EQUITY: Direction.CREDIT,
    GLType.INCOME: Direction.CREDIT,
}


def book_balance(normal_side: Direction, debit_total: int, credit_total: int) -> int:
    """Net of totals per normal side (balance-semantics.md)."""
    if normal_side == Direction.CREDIT:
        return credit_total - debit_total
    return debit_total - credit_total


def available_balance(book: int, held: int, pending_debit: int, overdraft_limit: int) -> int:
    return book - held - pending_debit + overdraft_limit


@dataclass(frozen=True, slots=True)
class PostingLine:
    balance_id: UUID
    direction: Direction
    money: Money

    def __post_init__(self) -> None:
        if not self.money.is_positive:
            raise ValidationFailedError("Posting amounts must be strictly positive.")


@dataclass(frozen=True, slots=True)
class EntrySpec:
    """One journal entry to post. ``purpose`` distinguishes multiple entries produced by
    the same business source (e.g. PRINCIPAL, FEE) and is part of the at-most-once key."""

    purpose: str
    lines: tuple[PostingLine, ...]
    description: str = ""
    value_date: date | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    reversal_of: UUID | None = None


@dataclass(frozen=True, slots=True)
class HoldChange:
    """Delta on a balance's held_amount (positive = place, negative = release/capture)."""

    balance_id: UUID
    delta_minor: int
    currency: str


def validate_entry(spec: EntrySpec) -> None:
    """Domain-level balance check per currency (the DB trigger is the backstop)."""
    if not spec.purpose or len(spec.purpose) > 40:
        raise ValidationFailedError("Entry purpose must be 1..40 characters.")
    if len(spec.lines) < 2:
        raise UnbalancedEntryError("A journal entry needs at least two postings.")
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for line in spec.lines:
        idx = 0 if line.direction == Direction.DEBIT else 1
        totals[line.money.currency][idx] += line.money.amount_minor
    for currency, (debits, credits) in sorted(totals.items()):
        if debits != credits:
            raise UnbalancedEntryError(
                f"Entry '{spec.purpose}' is unbalanced in {currency}: "
                f"debits {debits} != credits {credits} (minor units)."
            )


def net_effect(lines: Iterable[PostingLine]) -> dict[UUID, tuple[int, int]]:
    """Per balance: (debit_delta, credit_delta)."""
    effect: dict[UUID, list[int]] = defaultdict(lambda: [0, 0])
    for line in lines:
        idx = 0 if line.direction == Direction.DEBIT else 1
        effect[line.balance_id][idx] += line.money.amount_minor
    return {k: (v[0], v[1]) for k, v in effect.items()}


def mirror(lines: Sequence[PostingLine]) -> tuple[PostingLine, ...]:
    """Reversal lines: same balances and amounts, flipped directions."""
    flip = {Direction.DEBIT: Direction.CREDIT, Direction.CREDIT: Direction.DEBIT}
    return tuple(PostingLine(line.balance_id, flip[line.direction], line.money) for line in lines)
