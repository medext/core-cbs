# Balance Semantics Specification

| | |
|---|---|
| **Purpose** | Exact, unambiguous definitions of every balance figure and date the system exposes. The bare word "balance" is banned; these are the only legal terms. |
| **Audience** | Engineering, API consumers, operations, auditors. |
| **Owning phase** | Phase 0 (spec) → Phase 3/5 (implementation must match; same-change rule). |
| **Related** | [Ledger architecture](ledger-architecture.md) · [Transaction lifecycle](../domain/transaction-lifecycle.md) · [Glossary](../domain/glossary.md) |

## Stored figures (LedgerBalance projection fields)

All amounts are Money (integer minor units + currency, ADR-0004). "Signed per normal side"
means the figure is reported positive when the balance sits on its normal side.

| Field | Definition | Updated by |
|---|---|---|
| `ledger_debit_total` | Σ amounts of all posted DEBIT postings against this balance | Posting service, in-transaction |
| `ledger_credit_total` | Σ amounts of all posted CREDIT postings against this balance | Posting service, in-transaction |
| `book_balance` | Net of totals per normal side: for credit-normal (customer liability) `credit_total − debit_total`; for debit-normal `debit_total − credit_total` | Derived; stored for query performance |
| `held_amount` | Σ active (non-captured, non-released, non-expired) holds | Hold place/capture/release/expire, in-transaction |
| `pending_debit` | Σ amounts of business transactions in states that reserve outflow without postings (per lifecycle table: HELD via holds; QUEUED/AUTHORIZED outflows if product policy reserves them — MVP: only holds reserve) | Transactions context, in-transaction |
| `pending_credit` | Σ authorized-not-posted inflows (informational; **never** spendable) | Transactions context |
| `overdraft_limit` | Authorized negative headroom from the product/account configuration (0 if none) | Config activation |
| `version` | Optimistic-concurrency counter | Every projection write |

## Derived figures

```text
available_balance = book_balance − held_amount − pending_debit + overdraft_limit
cleared_balance   = book balance restricted to postings with value_date ≤ tenant business_date
```

- **`available_balance`** is the figure checked for funds sufficiency (invariant 18). Checked
  under row lock inside the posting transaction. `pending_credit` never contributes.
- **`cleared_balance`** supports value-dated economics (interest bases, availability policies
  for external instruments). MVP with same-day value dates: `cleared == book`; the field and
  its computation path exist from Phase 3 so value dating lands without schema change.
- Nothing else may be derived and exposed under a new name without updating this spec, the
  glossary, and the API docs in the same change.

## Date & timestamp semantics

| Field | Type | Meaning |
|---|---|---|
| `business_date` | date | Tenant's official banking day at posting; assigned by the business_day context; **not** server date |
| `value_date` | date | Date the amount affects economics (interest/clearing). Defaults to business_date; may be earlier (backdated item, posts into OPEN period) or later (forward-dated) |
| `posted_at` | timestamptz | Commit instant of the journal entry (server clock, UTC) |
| `created_at` | timestamptz | Row creation instant (intake) |
| `settlement_date` | date | Date external settlement completed (settlement-bearing operations) |
| `effective_date` | date | Configuration activation date (products/plans/rules) — never on postings |

Ordering guarantee: within one ledger, `(business_date, entry_seq)` gives the canonical
accounting order; `posted_at` is diagnostic, not accounting-ordering.

## Worked example (customer wallet, credit-normal, overdraft 0)

| Step | Event | book | held | pending_debit | available |
|---|---|---|---|---|---|
| 0 | Opening | 0.00 | 0 | 0 | 0.00 |
| 1 | Deposit posted +100.00 | 100.00 | 0 | 0 | 100.00 |
| 2 | Merchant hold 30.00 placed | 100.00 | 30.00 | 0 | 70.00 |
| 3 | Transfer out 50.00 posted | 50.00 | 30.00 | 0 | 20.00 |
| 4 | Attempt transfer 25.00 | — rejected: `INSUFFICIENT_FUNDS` (25.00 > 20.00) |
| 5 | Hold captured for 28.00 | 22.00 | 0 | 0 | 22.00 |
| 6 | Reversal of step 3 | 72.00 | 0 | 0 | 72.00 |

Partial capture rule (step 5): capture ≤ held amount posts the captured amount and releases
the remainder atomically in one transaction.

## Invariant checks on figures

- `book_balance ≡ f(ledger_debit_total, ledger_credit_total)` — recomputed by integrity runs.
- `held_amount ≡ Σ active holds` — cross-checked against hold records.
- Projection ≡ reconstruction from postings (invariant 9/10).
- `available_balance ≥ 0` for accounts without overdraft — enforced pre-commit under lock;
  DB backstop constraint per overdraft policy (design detail Phase 3/5).

## API exposure

The balances endpoint returns the full set — never a single unqualified `balance` field:

```json
{
  "currency": "XOF",
  "book_balance": "72.00",
  "available_balance": "72.00",
  "cleared_balance": "72.00",
  "held_amount": "0.00",
  "pending_debit": "0.00",
  "pending_credit": "0.00",
  "overdraft_limit": "0.00",
  "as_of": {"business_date": "2026-07-17", "entry_seq": 41}
}
```

Amount wire format (decimal string, minor-unit handling) is fixed in the API standards doc
and must match ADR-0004.
