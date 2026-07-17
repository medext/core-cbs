# ADR-0003 — PostgreSQL is the sole authority for financial state; Redis is never truth

- **Status:** Proposed (Phase 0 review)
- **Date:** 2026-07-17
- **Deciders:** pending human approval

## Context

Financial correctness (invariants 11, 13, 18, 23–25) demands one authoritative, ACID,
constraint-capable store. Caches and queues are operationally useful but epistemically
untrustworthy (eviction, replication lag, split brain).

## Decision

**PostgreSQL (16+ at Phase 1) is the final authority** for: journal entries, postings,
ledger balances, transaction state, idempotency records, business dates, accounting periods,
audit records, and outbox events. All financial writes are synchronous PostgreSQL
transactions guarded by row locks, constraints, and unique indexes.

**Redis** is admitted only for: caches, rate limiting, ephemeral coordination, and queue
transport — with the rule that losing Redis entirely may degrade performance or delay async
work but can never corrupt financial state or admit a double spend. Redis locks are never
the sole protection for any invariant.

## Alternatives considered

- **Event-store/CQRS-first (Kafka or ES as source of truth)** — rejected: complicates the
  synchronous funds check (the one thing a CBS must get right), adds heavy infra to
  on-premise installs; CQRS remains available for *read models* case-by-case (§4.1).
- **Distributed SQL (Cockroach/Yugabyte)** — rejected for now: operational unfamiliarity for
  on-prem customers, weaker ecosystem fit with Django; revisit only under proven scale needs.
- **Redis-assisted balance authority (hot balances in Redis, periodic flush)** — rejected:
  prohibited pattern ("cached balance as accounting authority"); race/eviction windows are
  double-spend windows.

## Consequences

- **Positive:** invariants enforceable with constraints/triggers/grants (defense-in-depth);
  single-transaction atomicity; simple mental model; on-prem customers can bring their own
  PostgreSQL.
- **Negative / accepted costs:** per-tenant throughput ceiling ≈ DB write capacity — accepted
  and managed via hot-balance strategy + capacity model; HA/failover design (Phase 9) must
  address synchronous-commit and replica semantics honestly (no silent RPO>0 claims).
- **Neutral:** exact PostgreSQL version pinned in Phase 1; failover/replication assumptions
  documented in backup/DR docs (OD-9).

## Compliance & security impact

Auditability: everything financial in one transactional store with grants revoking
UPDATE/DELETE on append-only tables; backup/restore story is a PostgreSQL story.

## Reversibility

Low need, high cost — this is a foundation choice. The repository/service seams keep SQL
behind application services, but leaving PostgreSQL would be a major program.
