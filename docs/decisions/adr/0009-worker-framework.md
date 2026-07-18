# ADR-0009 — Celery (reliability-configured) as the async worker framework

- **Status:** Proposed (decide at Phase 1 gate; wired in Phase 3)
- **Date:** 2026-07-18
- **Deciders:** pending human approval

## Context

Async workloads arrive in Phase 3+: outbox relay, webhook delivery, EoD steps, queued/bulk
transactions. Requirements: at-least-once execution with redelivery on worker death, explicit
queues/routing, scheduling (EoD, hold expiry), observability, Redis transport initially,
operational simplicity on-premise. Resolves OD-5. Crucially, ADR-0003/0007 make the queue
**transport only** — correctness never depends on broker semantics, which lowers the risk of
either choice.

## Decision

We will use **Celery** with a mandatory reliability configuration profile:
`acks_late=True`, `task_reject_on_worker_lost=True`, explicit named queues per workload
class (no default-queue dumping), `worker_prefetch_multiplier=1` for financial queues,
bounded retries with jittered backoff, and Celery Beat (or DB-driven scheduling for
business-date jobs — Phase 7 decides) for periodic work. Redis is the initial broker;
the outbox table remains the durable source of events.

**No worker dependency is added to the codebase until Phase 3** (first consumer: outbox
relay).

## Alternatives considered

- **Dramatiq** — genuinely attractive: safer defaults (acks-late semantics out of the box),
  smaller surface. Rejected on ecosystem grounds: thinner tooling/monitoring story, smaller
  hiring pool, fewer battle-tested operational patterns for on-prem customers; our
  reliability config closes Celery's default-semantics gap explicitly.
- **arq / RQ** — too thin for multi-queue routing + scheduling + observability needs.
- **Custom DB-polling workers only** — the outbox relay is DB-polling by design, but
  building all scheduling/retry machinery ourselves for every workload is undifferentiated
  effort; workers still add value above the relay.

## Consequences

- **Positive:** mature ecosystem (monitoring via Flower/OTel instrumentation), documented
  ops patterns, scheduling included; queue-partitioning option for hot balances (Phase 8+)
  is well-trodden.
- **Negative / accepted costs:** Celery's defaults are unsafe for our use — the reliability
  profile above is **mandatory and lint/review-enforced**; Redis-broker visibility-timeout
  redelivery quirks are tolerable because tasks are idempotent by construction (ADR-0006)
  and the outbox is the durable source.
- **Neutral:** broker can move to RabbitMQ later without touching task code.

## Compliance & security impact

Queue payloads carry IDs, not PII; workers re-validate against the DB. No new trust
boundary beyond TB6 in the threat model (already analyzed).

## Reversibility

Moderate: task bodies are thin application-service calls; swapping the worker framework
would touch wiring, not domain logic.
