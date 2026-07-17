# Rules — Ledger & Posting Engine (`src/next_core/ledger/`, `src/next_core/transactions/`)

These rules apply to any change touching the ledger kernel, posting engine, balances, or
transaction orchestration. Read `docs/accounting/ledger-architecture.md`,
`docs/accounting/invariants.md`, and `docs/accounting/balance-semantics.md` first.

## Immutability

- `JournalEntry` and `Posting` rows are **append-only**. No `UPDATE` or `DELETE` on posted rows,
  ever — not in application code, not in migrations, not in "fix" scripts.
- Corrections are new journal entries: reversals or compensating entries, linked to the original
  via an explicit reversal relationship. The link is mandatory, not metadata.
- Balance rows are projections. They may be updated only by the posting service inside the same
  DB transaction as the postings that justify the change, or rebuilt by the reconstruction
  command. Any other write path to a balance is a defect.

## Money

- Amounts are integers in minor units + ISO-4217 currency code (ADR-0004). `float` for money is
  forbidden anywhere, including tests, fixtures, and serializers. `Decimal` only at computation
  boundaries (rates, interest, fees), immediately quantized per the documented rounding policy.
- Every posting carries currency and direction (DEBIT/CREDIT). Never a signed "amount" without
  an explicit direction.
- Cross-currency entries must go through the explicitly modeled FX/clearing bridge — a journal
  entry must balance per currency.

## Posting service

- All postings go through the single posting service. No module may insert postings directly.
- The posting service runs in one synchronous DB transaction: validate → lock balances in
  deterministic order (by balance UUID) → check funds/limits → insert entry + postings →
  update projections → write outbox record → commit.
- Idempotency check happens inside that transaction, keyed by (tenant, operation, client, key).
- Never take application-level (Redis) locks as the sole guard. DB row locks + constraints are
  the authority.

## Database constraints are mandatory

For any ledger schema change, verify these exist and remain:
- CHECK: posting amount > 0; direction in (DEBIT, CREDIT).
- Deferred/trigger-enforced: per-entry, per-currency debit total = credit total.
- UNIQUE on idempotency (tenant_id, scope, key).
- FK from posting → journal entry → business transaction (traceable source, invariant 15).
- No FK with `ON DELETE CASCADE` from any financial table.

## Testing requirements (blocking)

A ledger change is not complete without, at minimum:
- Property-based tests (Hypothesis): debits == credits; reversal restores economic position;
  reconstruction matches projection.
- Concurrency tests on real PostgreSQL: double-spend attempts, duplicate idempotent requests,
  hold capture/release races, deadlock recovery. SQLite results are not evidence.
- A run of the balance-reconstruction command over the test dataset.

## Review

Before finishing, run the `ledger-accounting-reviewer` and `postgres-concurrency-reviewer`
subagents on the diff. Their objections must be resolved or explicitly escalated to the user —
never silently dismissed.
