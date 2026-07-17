# Rules — Testing (`tests/`)

Read `docs/testing/test-strategy.md` first.

## Non-negotiables

- Financial correctness claims require tests on **real PostgreSQL** (compose service or
  Testcontainers). SQLite is never evidence for constraints, isolation, locking, or
  concurrency behavior.
- No mock-only tests for financial logic: a test that validates only mocked behavior is a
  prohibited fake test. Mocks are acceptable at true external boundaries (IAM, webhook
  receivers, statement sources) — never for the ledger, balances, or the database.
- Concurrency tests are mandatory for: transfers, holds (capture/release races), limit
  consumption, reversals, closure, idempotent retries, deadlock recovery. They run real
  parallel transactions against PostgreSQL and assert invariants afterwards.
- Property-based tests (Hypothesis) are mandatory for money arithmetic, posting balance,
  reversal symmetry, idempotency, and balance reconstruction.

## Layout

```text
tests/
  unit/          Pure domain: value objects, state machines, fee/limit/interest calc
  property/      Hypothesis suites for invariants
  integration/   Real-PostgreSQL: constraints, transactions, locks, outbox, routing, migrations
  contract/      API/event schemas, webhook signatures, backward compatibility
  concurrency/   Parallel-execution invariant tests
  e2e/           Full business flows through the API
  performance/   Benchmarks & load profiles (Phase 9)
```

## Discipline

- Write tests before or alongside implementation — acceptance criteria first.
- Every bug fix ships with a regression test reproducing the bug.
- Never weaken, skip, or delete a failing invariant test to make a build pass — a failing
  invariant test stops the work and is escalated.
- Coverage thresholds are enforced in CI; do not game them with trivial assertions.
- Tests must be deterministic: no reliance on wall-clock timing, ordering luck, or shared
  mutable state between tests. Concurrency tests use explicit synchronization barriers, not
  sleeps.
- After any meaningful change, run the targeted tests for the touched module before moving on;
  run the full relevant gate (`make check`) before declaring work complete. Report actual
  results — never assume.
