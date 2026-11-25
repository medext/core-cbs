"""Atomic limit evaluation & consumption (called by transactions inside its DB transaction)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from django.db import connections

from next_core.limits.models import LimitCounter
from next_core.platform.errors import LimitExceededError
from next_core.platform.money import Money
from next_core.products.definition import LimitRule, LimitWindow, Operation
from next_core.tenancy.context import current_tenant


@dataclass(frozen=True, slots=True)
class LimitStatus:
    code: str
    window: str
    max_amount: Money | None
    consumed_amount: Money
    max_count: int | None
    consumed_count: int

    @property
    def remaining_amount(self) -> Money | None:
        if self.max_amount is None:
            return None
        return self.max_amount - self.consumed_amount


def window_key(window: LimitWindow, on: date) -> str:
    if window == LimitWindow.DAILY:
        return f"D{on.isoformat()}"
    if window == LimitWindow.MONTHLY:
        return f"M{on:%Y-%m}"
    return "T"


def _ensure_counters(account_id: UUID, keys: Sequence[tuple[str, str, str]]) -> None:
    ctx = current_tenant()
    with connections[ctx.db_alias].cursor() as cur:
        for code, currency, wkey in keys:
            cur.execute(
                "INSERT INTO limit_counter (tenant_id, account_id, limit_code, currency, "
                "window_key, consumed_amount, consumed_count, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, 0, 0, now()) ON CONFLICT DO NOTHING",
                [str(ctx.tenant_id), str(account_id), code, currency, wkey],
            )


def consume(
    account_id: UUID,
    rules: Sequence[LimitRule],
    operation: Operation,
    amount: Money,
    on: date,
    *,
    dry_run: bool = False,
) -> list[LimitStatus]:
    """Check (and unless dry_run, consume) every applicable limit; raise LIMIT_EXCEEDED.

    Must run inside the caller's transaction after the account row lock. Counters are
    locked in deterministic (limit_code, window_key) order."""
    applicable = sorted(
        (r for r in rules if operation in r.operations), key=lambda r: (r.code, r.window.value)
    )
    statuses: list[LimitStatus] = []
    windowed = [r for r in applicable if r.window != LimitWindow.TRANSACTION]
    counters: dict[str, LimitCounter] = {}
    if windowed:
        keys = [(r.code, amount.currency, window_key(r.window, on)) for r in windowed]
        if not dry_run:
            _ensure_counters(account_id, keys)
            qs = LimitCounter.objects.select_for_update()
        else:
            qs = LimitCounter.objects.all()
        for row in qs.filter(
            account_id=account_id,
            currency=amount.currency,
            limit_code__in=[k[0] for k in keys],
            window_key__in=[k[2] for k in keys],
        ).order_by("limit_code", "window_key"):
            counters[row.limit_code] = row

    for rule in applicable:
        max_amount = (
            Money(rule.max_amount[amount.currency], amount.currency) if rule.max_amount else None
        )
        counter = counters.get(rule.code)
        used_amount = counter.consumed_amount if counter else 0
        used_count = counter.consumed_count if counter else 0
        if rule.window == LimitWindow.TRANSACTION:
            used_amount, used_count = 0, 0
        if max_amount is not None and used_amount + amount.amount_minor > max_amount.amount_minor:
            raise LimitExceededError(
                f"Limit {rule.code} ({rule.window.value}) exceeded: remaining "
                f"{Money(max(max_amount.amount_minor - used_amount, 0), amount.currency)}, "
                f"requested {amount}.",
                extra={"limit": {"code": rule.code, "window": rule.window.value}},
            )
        if rule.max_count is not None and used_count + 1 > rule.max_count:
            raise LimitExceededError(
                f"Limit {rule.code} ({rule.window.value}) count of {rule.max_count} reached.",
                extra={"limit": {"code": rule.code, "window": rule.window.value}},
            )
        if counter is not None and not dry_run:
            counter.consumed_amount = used_amount + amount.amount_minor
            counter.consumed_count = used_count + 1
            counter.save(update_fields=["consumed_amount", "consumed_count", "updated_at"])
        statuses.append(
            LimitStatus(
                rule.code,
                rule.window.value,
                max_amount,
                Money(used_amount + amount.amount_minor, amount.currency),
                rule.max_count,
                used_count + 1,
            )
        )
    return statuses


def current_usage(
    account_id: UUID, rules: Sequence[LimitRule], currency: str, on: date
) -> list[LimitStatus]:
    out: list[LimitStatus] = []
    for rule in sorted(rules, key=lambda r: r.code):
        if rule.window == LimitWindow.TRANSACTION:
            continue
        row = LimitCounter.objects.filter(
            account_id=account_id,
            limit_code=rule.code,
            currency=currency,
            window_key=window_key(rule.window, on),
        ).first()
        out.append(
            LimitStatus(
                rule.code,
                rule.window.value,
                Money(rule.max_amount[currency], currency) if rule.max_amount else None,
                Money(row.consumed_amount if row else 0, currency),
                rule.max_count,
                row.consumed_count if row else 0,
            )
        )
    return out
