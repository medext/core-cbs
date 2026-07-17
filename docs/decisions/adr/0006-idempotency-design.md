# ADR-0006 — Idempotency: DB-arbitrated, scoped keys, hash-verified, response-replaying

- **Status:** Proposed (Phase 0 review)
- **Date:** 2026-07-17
- **Deciders:** pending human approval

## Context

Invariants 11–12: retries must not double-post; key reuse with a different payload must
conflict. Clients face ambiguous outcomes (timeout after commit). Concurrency makes
check-then-act approaches unsound.

## Decision

- Every financial write requires a client `Idempotency-Key`.
- **Scope:** `(tenant, API operation, API client, key)` — unique-constrained in the tenant DB.
- **Arbitration by the database:** `INSERT … ON CONFLICT` of the idempotency record inside
  the same transaction as the postings; the unique constraint decides races, not application
  reads or Redis.
- Stored: canonicalized **request hash** (conflict detection), processing **status**, final
  **response snapshot**, and the produced journal-entry reference — enabling exact replay of
  the original result on retry and deterministic `409 IDEMPOTENCY_CONFLICT` on payload
  mismatch. In-flight duplicates receive a retryable conflict (never a second execution).
- Record commits/rolls back **atomically with the postings** — closing the crash window
  between "posted" and "recorded".
- **Retention:** financial-write records kept for the audit/dispute horizon (default 10 y,
  OD-8) with archival; non-financial 30 d. Expiry only after terminal status.

Full protocol & race analysis: [idempotency-concurrency](../../architecture/idempotency-concurrency.md).

## Alternatives considered

- **Redis-based idempotency cache** — rejected as authority: eviction/failover reopens the
  double-posting window (prohibited: Redis-only correctness). Admissible later as a
  fast-path *hint* in front of the DB record, never instead of it.
- **Natural-key dedup (dedupe on payload hash alone)** — rejected: legitimately identical
  business requests (two 10.00 transfers same accounts) must both execute when keys differ.
- **Middleware-generic idempotency (framework plugin, separate store/transaction)** —
  rejected: records outside the posting transaction reintroduce the partial-commit window.

## Consequences

- **Positive:** at-most-once posting under crashes, races, and ambiguous networks; auditable
  request→entry linkage; simple, stated client contract ("retry with the same key").
- **Negative / accepted costs:** response snapshots consume storage (bounded, archivable);
  every financial endpoint must integrate the gate (enforced by API rules + contract tests);
  long-idle `PROCESSING` rows need a sweeper tied to the transaction-lifecycle recovery rules.
- **Neutral:** header name & error codes fixed in API standards.

## Compliance & security impact

Idempotency records double as dispute evidence; the key is client data — validated, size-
bounded, never interpreted.

## Reversibility

None sought — this is the safety contract of the public API.
