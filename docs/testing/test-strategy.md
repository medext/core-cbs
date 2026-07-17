# Test Strategy

| | |
|---|---|
| **Purpose** | The testing pyramid, what each layer proves, and the gate-blocking suites. |
| **Audience** | Engineering, `test-engineer` subagent. |
| **Owning phase** | Phase 0 (strategy) → Phase 1 (framework) → continuously. |
| **Related** | `.claude/rules/testing.md` · [Invariants](../accounting/invariants.md) · [Concurrency suite](../architecture/idempotency-concurrency.md) |

## Principles

1. Tests **prove** financial correctness; they never simulate it. Mock-only tests of
   financial logic are prohibited fake tests.
2. Database behavior is proven on **real PostgreSQL** (Testcontainers or compose service).
   SQLite is never evidence.
3. Property-based testing (Hypothesis) is a first-class layer for invariants, not a bonus.
4. Tests are written before or alongside implementation, from acceptance criteria.
5. A failing invariant test stops the line (never skipped/weakened to pass a build).

## The pyramid

| Layer | Directory | Proves | Infrastructure | Examples |
|---|---|---|---|---|
| Unit | `tests/unit/` | Pure domain rules | None (no DB) | Money arithmetic & rounding; state-machine transitions; fee/limit/interest calculations; posting-rule resolution; authorization policy decisions; product rules |
| Property | `tests/property/` | Invariants over generated inputs | None or PostgreSQL per property | Σdebits=Σcredits for random entries; reversal restores economic position; idempotent replay creates no postings; random transfer sequences conserve money; invalid currency mixes rejected; reconstruction == projection |
| Integration | `tests/integration/` | DB truth | Real PostgreSQL | Constraints & triggers fire on violating writes; transaction atomicity under fault injection; lock behavior; deadlock recovery; outbox commit-coupling; tenant routing; migration forward(+rollback) runs |
| Contract | `tests/contract/` | Interface stability | Schemathesis/spectacular checks, snapshot schemas | OpenAPI matches implementation; error-catalog codes stable; event schema versioning; webhook signature verification; IAM claim-mapping boundary; statement-adapter contracts; backward-compat vs. previous released schema |
| Concurrency | `tests/concurrency/` | Hostile parallelism | Real PostgreSQL, parallel workers, barriers | The full suite in [idempotency-concurrency](../architecture/idempotency-concurrency.md) — double spend, duplicate keys, hold races, limit overconsumption, A→B/B→A storms, kill-mid-transaction, ambiguous retry |
| E2E | `tests/e2e/` | Business flows through the API | Full compose stack (app+PG+Redis+Keycloak dev) | open customer+account → fund → transfer → hold → capture/release → fee → reverse → statement → reconcile external txn → close business day → close account |
| Performance | `tests/performance/` | Capacity model & resilience | Dedicated environment (Phase 9) | Hot balances, high-cardinality accounts, queue lag, DB contention, worker/app restart mid-processing, duplicate event delivery, network timeout post-commit, failover assumptions, backup/restore, migration under load |

## Execution matrix

| Suite | Per-change (targeted) | Every PR (CI) | Nightly | Phase gate |
|---|---|---|---|---|
| Unit + property | touched modules | ✅ full | ✅ | ✅ |
| Integration | touched modules | ✅ full | ✅ | ✅ |
| Contract | touched APIs | ✅ | ✅ | ✅ |
| Concurrency | on ledger-touching diffs | ledger-touching PRs | ✅ full | ✅ full |
| E2E | — | smoke subset | ✅ full | ✅ full |
| Performance | — | — | — | Phase 9 gates |

Coverage: thresholds set in Phase 1 (line + branch on `src/next_core/`); financial contexts
(ledger, transactions, pricing, limits) target strictly higher thresholds than platform code.
Coverage is a floor, not proof — the `test-engineer` audit is the quality control.

## Test data & fixtures

- Deterministic factories per context (no random data outside Hypothesis's controlled
  generators); currency-diverse fixtures (0-, 2-, 3-exponent currencies) mandatory in money
  tests.
- Seed institution fixture (mini CoA + 2 products) shared by integration/e2e — versioned with
  the code, matching the Phase 10 demo catalog direction.
- No production or real-customer data in tests, ever.

## Tooling (Phase 1 setup)

pytest + pytest-django + pytest-xdist (parallel) + Hypothesis + Testcontainers (or compose
services in CI) + schemathesis (contract) + coverage.py. Concurrency harness: process/thread
workers with explicit barriers (no sleeps) — provided as a shared fixture library in
`tests/concurrency/harness.py`.
