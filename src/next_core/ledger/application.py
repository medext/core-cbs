"""Ledger application services — THE single write path for financial state.

Only the ``transactions`` context calls the write functions here (golden rule 2; enforced by
``tests/unit/test_architecture_boundaries.py``). Every write runs inside one DB transaction:

    validate → lock balances (ORDER BY id) → funds check on locked rows → INSERT entries +
    postings → force deferred balance checks → UPDATE projections (version += 1) → outbox

The database independently enforces balance, append-only, writer-session, and funds-floor
rules (migration 0002) — application checks fail first with typed errors, the database is
the backstop.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from django.db import IntegrityError, connections, transaction

from next_core.ledger.domain import (
    NORMAL_SIDE,
    Direction,
    EntrySpec,
    GLType,
    HoldChange,
    PostingLine,
    available_balance,
    book_balance,
    mirror,
    net_effect,
    validate_entry,
)
from next_core.ledger.models import GLAccount, JournalEntry, LedgerBalance, Posting
from next_core.platform import clock
from next_core.platform.errors import (
    ConflictStateError,
    CurrencyMismatchError,
    InsufficientFundsError,
    NotFoundError,
    ValidationFailedError,
)
from next_core.platform.money import Money, get_currency
from next_core.platform.outbox.service import emit
from next_core.tenancy.context import current_tenant

# ------------------------------------------------------------------------------ views


@dataclass(frozen=True, slots=True)
class BalanceView:
    id: UUID
    currency: str
    normal_side: str
    gl_code: str
    owner_type: str
    owner_id: UUID | None
    purpose: str
    debit_total: int
    credit_total: int
    book_balance: int
    held_amount: int
    pending_debit: int
    pending_credit: int
    overdraft_limit: int
    funds_enforced: bool
    version: int
    last_entry_seq: int

    @property
    def available_balance(self) -> int:
        return available_balance(
            self.book_balance, self.held_amount, self.pending_debit, self.overdraft_limit
        )

    def money(self, minor: int) -> Money:
        return Money(minor, self.currency)


@dataclass(frozen=True, slots=True)
class EntryView:
    id: UUID
    seq: int
    purpose: str
    source_type: str
    source_id: UUID
    business_date: date
    value_date: date
    reversal_of: UUID | None
    lines: tuple[PostingLine, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class PostingRequest:
    source_type: str
    source_id: UUID
    entries: tuple[EntrySpec, ...] = ()
    hold_changes: tuple[HoldChange, ...] = ()
    business_date: date | None = None
    allow_overdraw: bool = False


@dataclass(frozen=True, slots=True)
class PostingResult:
    entries: tuple[EntryView, ...]
    balances: dict[UUID, BalanceView]


def _view(b: LedgerBalance, gl_code: str | None = None) -> BalanceView:
    return BalanceView(
        id=b.id,
        currency=b.currency,
        normal_side=b.normal_side,
        gl_code=gl_code if gl_code is not None else b.gl_account.code,
        owner_type=b.owner_type,
        owner_id=b.owner_id,
        purpose=b.purpose,
        debit_total=b.debit_total,
        credit_total=b.credit_total,
        book_balance=b.book_balance,
        held_amount=b.held_amount,
        pending_debit=b.pending_debit,
        pending_credit=b.pending_credit,
        overdraft_limit=b.overdraft_limit,
        funds_enforced=b.funds_enforced,
        version=b.version,
        last_entry_seq=b.last_entry_seq,
    )


def _alias() -> str:
    return current_tenant().db_alias


def _writer_session(allow_overdraw: bool) -> None:
    """Transaction-local flags read by the DB triggers (reverted with the (sub)transaction)."""
    with connections[_alias()].cursor() as cur:
        cur.execute(
            "SELECT set_config('next_core.ledger_writer', 'on', true), "
            "set_config('next_core.allow_overdraw', %s, true)",
            ["on" if allow_overdraw else "off"],
        )


def _end_writer_session() -> None:
    with connections[_alias()].cursor() as cur:
        cur.execute(
            "SELECT set_config('next_core.ledger_writer', 'off', true), "
            "set_config('next_core.allow_overdraw', 'off', true)"
        )


def _force_deferred_checks() -> None:
    """Fire the deferred balanced-entry triggers now (inside our savepoint), so a defect
    surfaces as a clean rollback of this call rather than at the caller's COMMIT."""
    with connections[_alias()].cursor() as cur:
        cur.execute(
            "SET CONSTRAINTS ledger_entry_balanced_posting, ledger_entry_balanced_entry IMMEDIATE"
        )
        cur.execute(
            "SET CONSTRAINTS ledger_entry_balanced_posting, ledger_entry_balanced_entry DEFERRED"
        )


# ------------------------------------------------------------------------------ CoA


@dataclass(frozen=True, slots=True)
class GLSeed:
    code: str
    name: str
    type: GLType
    parent_code: str = ""


def ensure_gl_accounts(seeds: Iterable[GLSeed]) -> int:
    """Idempotently create GL accounts (existing codes are left untouched)."""
    tenant_id = current_tenant().tenant_id
    created = 0
    with transaction.atomic(using=_alias()):
        for seed in seeds:
            _, was_created = GLAccount.objects.get_or_create(
                tenant_id=tenant_id,
                code=seed.code,
                defaults={
                    "name": seed.name,
                    "type": seed.type.value,
                    "normal_side": NORMAL_SIDE[seed.type].value,
                    "parent_code": seed.parent_code,
                },
            )
            created += int(was_created)
    return created


def gl_account(code: str) -> GLAccount:
    try:
        return GLAccount.objects.get(code=code, is_active=True)
    except GLAccount.DoesNotExist as exc:
        raise NotFoundError(f"GL account '{code}' does not exist.") from exc


def list_gl_accounts() -> list[GLAccount]:
    return list(GLAccount.objects.order_by("code"))


# ------------------------------------------------------------------------------ balances


def open_balance(
    *,
    gl_code: str,
    currency: str,
    owner_id: UUID,
    purpose: str = "PRINCIPAL",
    funds_enforced: bool = False,
    overdraft_limit: int = 0,
) -> BalanceView:
    """Create an (empty) customer-account balance mapped to a GL account."""
    get_currency(currency)
    if overdraft_limit < 0:
        raise ValidationFailedError("Overdraft limit cannot be negative.")
    gl = gl_account(gl_code)
    balance = LedgerBalance.objects.create(
        tenant_id=current_tenant().tenant_id,
        gl_account=gl,
        currency=currency,
        normal_side=gl.normal_side,
        owner_type="ACCOUNT",
        owner_id=owner_id,
        purpose=purpose,
        funds_enforced=funds_enforced,
        overdraft_limit=overdraft_limit,
    )
    return _view(balance, gl.code)


def internal_balance(gl_code: str, currency: str, purpose: str = "INTERNAL") -> BalanceView:
    """The institution's single ledger balance for (GL account, currency) — get or create.

    Race-safe: concurrent creators converge on the partial unique index."""
    get_currency(currency)
    gl = gl_account(gl_code)
    tenant_id = current_tenant().tenant_id
    existing = LedgerBalance.objects.filter(
        owner_type="INTERNAL", gl_account=gl, currency=currency, purpose=purpose
    ).first()
    if existing is not None:
        return _view(existing, gl.code)
    try:
        with transaction.atomic(using=_alias()):
            created = LedgerBalance.objects.create(
                tenant_id=tenant_id,
                gl_account=gl,
                currency=currency,
                normal_side=gl.normal_side,
                owner_type="INTERNAL",
                owner_id=None,
                purpose=purpose,
            )
        return _view(created, gl.code)
    except IntegrityError:
        found = LedgerBalance.objects.get(
            owner_type="INTERNAL", gl_account=gl, currency=currency, purpose=purpose
        )
        return _view(found, gl.code)


def get_balance(balance_id: UUID) -> BalanceView:
    try:
        b = LedgerBalance.objects.select_related("gl_account").get(id=balance_id)
    except LedgerBalance.DoesNotExist as exc:
        raise NotFoundError("Ledger balance not found.") from exc
    return _view(b)


def balances_for_owner(owner_id: UUID) -> list[BalanceView]:
    qs = LedgerBalance.objects.select_related("gl_account").filter(owner_id=owner_id)
    return [_view(b) for b in qs.order_by("purpose", "currency")]


def set_balance_policy(
    balance_id: UUID, *, funds_enforced: bool, overdraft_limit: int
) -> BalanceView:
    """Change the funds policy of a balance (config activation). Never touches value.

    Reducing a limit below current usage is allowed (the account becomes over-limit and
    further debits are refused) — hence allow_overdraw for this write only."""
    if overdraft_limit < 0:
        raise ValidationFailedError("Overdraft limit cannot be negative.")
    with transaction.atomic(using=_alias()):
        b = (
            LedgerBalance.objects.select_for_update()
            .select_related("gl_account")
            .get(id=balance_id)
        )
        _writer_session(allow_overdraw=True)
        LedgerBalance.objects.filter(id=b.id, version=b.version).update(
            funds_enforced=funds_enforced, overdraft_limit=overdraft_limit, version=b.version + 1
        )
        _end_writer_session()
        b.refresh_from_db()
        return _view(b)


# ------------------------------------------------------------------------------ posting


def _lock_balances(ids: Iterable[UUID]) -> dict[UUID, LedgerBalance]:
    """SELECT … FOR UPDATE in deterministic (UUID ascending) order — no lock-order deadlocks."""
    wanted = sorted(set(ids))
    locked = list(
        LedgerBalance.objects.select_for_update(of=("self",))
        .select_related("gl_account")
        .filter(id__in=wanted)
        .order_by("id")
    )
    found = {b.id: b for b in locked}
    missing = [i for i in wanted if i not in found]
    if missing:
        raise NotFoundError("One or more ledger balances do not exist.")
    return found


def post(request: PostingRequest) -> PostingResult:
    """Post journal entries and/or hold changes atomically. See module docstring."""
    ctx = current_tenant()
    if not request.entries and not request.hold_changes:
        raise ValidationFailedError("Nothing to post.")
    for spec in request.entries:
        validate_entry(spec)
    business_date = request.business_date or clock.business_date()

    all_lines = [line for spec in request.entries for line in spec.lines]
    ids = {line.balance_id for line in all_lines} | {h.balance_id for h in request.hold_changes}

    with transaction.atomic(using=ctx.db_alias):
        balances = _lock_balances(ids)
        before = {bid: _view(b) for bid, b in balances.items()}

        # Currency coherence on locked rows.
        for line in all_lines:
            if balances[line.balance_id].currency != line.money.currency:
                raise CurrencyMismatchError(
                    f"Posting currency {line.money.currency} does not match the balance "
                    f"currency {balances[line.balance_id].currency}."
                )
        for h in request.hold_changes:
            if balances[h.balance_id].currency != h.currency:
                raise CurrencyMismatchError("Hold currency does not match the balance currency.")

        # Compute new projections.
        effect = net_effect(all_lines)
        hold_delta: dict[UUID, int] = defaultdict(int)
        for h in request.hold_changes:
            hold_delta[h.balance_id] += h.delta_minor

        new_state: dict[UUID, dict[str, int]] = {}
        for bid, b in balances.items():
            d, c = effect.get(bid, (0, 0))
            debit_total = b.debit_total + d
            credit_total = b.credit_total + c
            held = b.held_amount + hold_delta.get(bid, 0)
            if held < 0:
                raise ConflictStateError("Hold release exceeds the held amount.")
            book = book_balance(Direction(b.normal_side), debit_total, credit_total)
            new_avail = available_balance(book, held, b.pending_debit, b.overdraft_limit)
            old_avail = before[bid].available_balance
            if (
                b.funds_enforced
                and new_avail < 0
                and new_avail < old_avail
                and not request.allow_overdraw
            ):
                needed = Money(old_avail - new_avail, b.currency)
                raise InsufficientFundsError(
                    f"Available balance {Money(max(old_avail, 0), b.currency)} is less than "
                    f"the requested {needed}.",
                    extra={"balance_id": str(bid)},
                )
            new_state[bid] = {
                "debit_total": debit_total,
                "credit_total": credit_total,
                "book_balance": book,
                "held_amount": held,
            }

        _writer_session(request.allow_overdraw)
        entry_views: list[EntryView] = []
        last_seq_for: dict[UUID, int] = {}
        try:
            for spec in request.entries:
                entry = JournalEntry(
                    tenant_id=ctx.tenant_id,
                    source_type=request.source_type,
                    source_id=request.source_id,
                    purpose=spec.purpose,
                    business_date=business_date,
                    value_date=spec.value_date or business_date,
                    description=spec.description[:200],
                    reversal_of_id=spec.reversal_of,
                    metadata=spec.metadata,
                )
                with transaction.atomic(using=ctx.db_alias):
                    entry.save()
                Posting.objects.bulk_create(
                    [
                        Posting(
                            tenant_id=ctx.tenant_id,
                            entry_id=entry.id,
                            balance_id=line.balance_id,
                            line_no=i,
                            direction=line.direction.value,
                            amount=line.money.amount_minor,
                            currency=line.money.currency,
                        )
                        for i, line in enumerate(spec.lines, start=1)
                    ]
                )
                for line in spec.lines:
                    last_seq_for[line.balance_id] = entry.seq
                entry_views.append(
                    EntryView(
                        id=entry.id,
                        seq=entry.seq,
                        purpose=entry.purpose,
                        source_type=entry.source_type,
                        source_id=entry.source_id,
                        business_date=entry.business_date,
                        value_date=entry.value_date,
                        reversal_of=spec.reversal_of,
                        lines=spec.lines,
                    )
                )
        except IntegrityError as exc:
            raise ConflictStateError(
                "This business source already produced that journal entry (or the entry "
                "was already reversed)."
            ) from exc
        if request.entries:
            _force_deferred_checks()

        for bid, state in new_state.items():
            b = balances[bid]
            updated = LedgerBalance.objects.filter(id=bid, version=b.version).update(
                **state,
                version=b.version + 1,
                last_entry_seq=max(b.last_entry_seq, last_seq_for.get(bid, 0)),
            )
            if updated != 1:  # pragma: no cover - impossible under the row lock
                raise ConflictStateError("Concurrent projection write detected.")
        _end_writer_session()

        for ev in entry_views:
            emit(
                "journal_entry.reversed" if ev.reversal_of else "journal_entry.posted",
                aggregate_type="journal_entry",
                aggregate_id=str(ev.id),
                payload={
                    "entry_id": str(ev.id),
                    "seq": ev.seq,
                    "purpose": ev.purpose,
                    "source": {"type": ev.source_type, "id": str(ev.source_id)},
                    "business_date": ev.business_date.isoformat(),
                    "reversal_of": str(ev.reversal_of) if ev.reversal_of else None,
                    "postings": [
                        {
                            "balance_id": str(line.balance_id),
                            "direction": line.direction.value,
                            "amount": line.money.to_wire(),
                            "currency": line.money.currency,
                        }
                        for line in ev.lines
                    ],
                },
            )

        refreshed = {
            b.id: _view(b)
            for b in LedgerBalance.objects.select_related("gl_account").filter(id__in=ids)
        }
    return PostingResult(entries=tuple(entry_views), balances=refreshed)


def entry_lines(entry: JournalEntry) -> tuple[PostingLine, ...]:
    return tuple(
        PostingLine(p.balance_id, Direction(p.direction), Money(p.amount, p.currency))
        for p in entry.postings.order_by("line_no")
    )


def reversal_specs(entry_ids: Sequence[UUID]) -> tuple[EntrySpec, ...]:
    """Mirror entries for ``entry_ids`` (caller posts them with allow_overdraw=True).

    The OneToOne ``reversal_of`` column guarantees at most one reversal per entry at the
    database level (concurrent second reversal → ConflictStateError)."""
    specs: list[EntrySpec] = []
    entries = JournalEntry.objects.filter(id__in=list(entry_ids)).order_by("seq")
    if len(entries) != len(set(entry_ids)):
        raise NotFoundError("Journal entry not found.")
    for entry in entries:
        if JournalEntry.objects.filter(reversal_of__id=entry.id).exists():
            raise ConflictStateError("Journal entry is already reversed.")
        if entry.reversal_of_id is not None:
            raise ConflictStateError("A reversal entry cannot itself be reversed.")
        specs.append(
            EntrySpec(
                purpose=f"REV:{entry.seq}"[:40],
                lines=mirror(entry_lines(entry)),
                description=f"Reversal of entry {entry.seq}",
                reversal_of=entry.id,
            )
        )
    return tuple(specs)


def entries_for_source(source_type: str, source_id: UUID) -> list[EntryView]:
    out: list[EntryView] = []
    for e in JournalEntry.objects.filter(source_type=source_type, source_id=source_id).order_by(
        "seq"
    ):
        out.append(
            EntryView(
                id=e.id,
                seq=e.seq,
                purpose=e.purpose,
                source_type=e.source_type,
                source_id=e.source_id,
                business_date=e.business_date,
                value_date=e.value_date,
                reversal_of=e.reversal_of_id,
                lines=entry_lines(e),
            )
        )
    return out


@dataclass(frozen=True, slots=True)
class StatementLine:
    entry_id: UUID
    entry_seq: int
    posting_id: int
    business_date: date
    value_date: date
    posted_at: Any
    direction: str
    amount_minor: int
    currency: str
    description: str
    source_type: str
    source_id: UUID
    running_book_balance: int


def statement(
    balance_id: UUID, *, after_posting_id: int = 0, limit: int = 50
) -> tuple[list[StatementLine], bool]:
    """Postings on one balance in accounting order with the running book balance.

    Cursor pagination by posting id (stable, monotonic). The opening running figure for a
    page is computed from all earlier postings (exact — never cached)."""
    b = LedgerBalance.objects.get(id=balance_id)
    side = Direction(b.normal_side)
    prior = Posting.objects.filter(balance_id=balance_id, id__lte=after_posting_id)
    running = 0
    for direction, amount in prior.values_list("direction", "amount").iterator():
        running += amount if direction == side.value else -amount
    rows = list(
        Posting.objects.select_related("entry")
        .filter(balance_id=balance_id, id__gt=after_posting_id)
        .order_by("id")[: limit + 1]
    )
    has_more = len(rows) > limit
    lines: list[StatementLine] = []
    for p in rows[:limit]:
        running += p.amount if p.direction == side.value else -p.amount
        lines.append(
            StatementLine(
                entry_id=p.entry.id,
                entry_seq=p.entry.seq,
                posting_id=p.id,
                business_date=p.entry.business_date,
                value_date=p.entry.value_date,
                posted_at=p.entry.posted_at,
                direction=p.direction,
                amount_minor=p.amount,
                currency=p.currency,
                description=p.entry.description,
                source_type=p.entry.source_type,
                source_id=p.entry.source_id,
                running_book_balance=running,
            )
        )
    return lines, has_more
