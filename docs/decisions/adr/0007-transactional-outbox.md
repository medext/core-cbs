# ADR-0007 — Transactional outbox for event publication; inbox deduplication for consumption

- **Status:** Proposed (Phase 0 review)
- **Date:** 2026-07-17
- **Deciders:** pending human approval

## Context

Invariant 25: events only after authoritative commit. Webhooks and internal async work must
never observe uncommitted state, and a commit must never fail to (eventually) emit its
events. Dual-write (DB + broker in one code path) is unsound.

## Decision

- **Outbox:** every domain event is INSERTed into a per-tenant `outbox_event` table **inside
  the same transaction** as the state change. A relay worker polls (`FOR UPDATE SKIP LOCKED`,
  batch, ordered per aggregate), delivers to consumers (webhook dispatcher, internal queues),
  marks delivered, with retries + exponential backoff + dead-letter status + replay tooling.
- **Delivery semantics: at-least-once**, ordered per aggregate (not globally). Consumers are
  told to deduplicate.
- **Inbox:** internal consumers record processed event IDs (`inbox` table, unique) in the
  same transaction as their side effects — exactly-once *effect* from at-least-once delivery.
- **Webhooks:** signed (HMAC, per-tenant secret, timestamp + replay window), event catalog
  versioned, endpoint suspension on sustained failure, delivery logs queryable.
- Broker choice (Redis-backed worker queue initially) is transport only; the outbox table is
  the durable source (ADR-0003 spirit: losing the transport loses nothing).

## Alternatives considered

- **Publish directly after commit (post-commit hook)** — rejected: crash between commit and
  publish silently loses events; no durable retry/replay/audit.
- **CDC/logical decoding (Debezium)** — rejected initially: heavy operational dependency for
  on-premise/air-gapped installs; revisit by ADR if outbox-poll lag becomes material.
- **Event-sourcing the ledger itself** — out of scope; the ledger is already append-only,
  and the journal is the source of truth (events are notifications, not truth).

## Consequences

- **Positive:** invariant 25 by construction; replayable, auditable event history; on-prem
  needs no broker beyond Redis; webhook reliability machinery (retry/DLQ/replay) is uniform.
- **Negative / accepted costs:** relay lag is a monitored metric (outbox lag alert);
  outbox table growth needs archival policy; per-aggregate ordering only — documented to
  consumers.
- **Neutral:** exact relay batching/backoff parameters tuned in Phase 3/9 with benchmarks.

## Compliance & security impact

Webhook signing + replay-window verification are mandatory (never trust unverified
webhooks — both directions); event payloads follow PII-minimization rules (IDs over data).

## Reversibility

Transport behind the relay is swappable (queue → broker → CDC) without touching producers.
