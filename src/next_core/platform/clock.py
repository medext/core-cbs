"""Clock & business-date provider (shared kernel).

Business date semantics (docs/accounting/balance-semantics.md): the tenant's official
banking day. Until the business_day context lands (Phase 7), the business date is the UTC
calendar date of the posting instant — registered as an assumption (OD-28). All callers go
through ``business_date()`` so the Phase 7 swap is a single-point change.
"""

from datetime import UTC, date, datetime


def now() -> datetime:
    return datetime.now(tz=UTC)


def business_date() -> date:
    return now().date()
