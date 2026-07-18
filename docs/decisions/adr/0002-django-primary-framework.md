# ADR-0002 — Django + DRF as the primary framework; FastAPI only by future justification

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** mohamed@next.mr — approved 2026-07-18 (Phase 0 gate)

## Context

The stack mandate (master prompt §3) sets Python/Django/DRF/PostgreSQL. We must still decide
how Django is used (it must not swallow the domain) and when FastAPI would be admissible.

## Decision

We will use **Django (latest LTS at Phase 1 start) + Django REST Framework** for the entire
application: configuration, admin/back-office, tenancy, parties, products, accounts, APIs,
authorization integration, and operational workflows. Domain logic lives in framework-free
`domain/` + `application/` layers per context; Django models/serializers/views are adapters
(hexagonal-lite — full hexagonal ceremony only where it pays, per §4.1).

Async workloads use a worker framework chosen in Phase 1 (Celery vs. Dramatiq — OD-13) driven
by the outbox relay, webhooks, EoD steps.

**FastAPI is not used initially.** It may be introduced only by a future ADR demonstrating an
independently deployable, genuinely isolated boundary (high-throughput ingestion, streaming
gateway) — never for the ledger or transaction orchestration.

## Alternatives considered

- **FastAPI everywhere** — rejected: loses Django's admin (real back-office value), mature
  ORM migrations, deployment checks, and ecosystem; async-first buys little for a
  synchronous-transactional core whose bottleneck is the DB transaction.
- **Django + FastAPI hybrid now** — rejected: two frameworks, two auth stacks, two OpenAPI
  pipelines from day one without a proven need (§4.2 requires an ADR with evidence).
- **Fat-Django idiom (logic in models/views/serializers)** — rejected: prohibited pattern
  (§20); untestable domain, framework lock-in of financial rules.

## Consequences

- **Positive:** one coherent stack; admin for back-office; DRF for versioned APIs; Django
  deployment checks feed the security baseline; hiring/operability realistic.
- **Negative / accepted costs:** Django ORM used carefully for financial writes (explicit
  transactions, `select_for_update`, raw constraint DDL in migrations); DRF serializer
  discipline (allow-lists) enforced by rules/review. Async story is worker-based, not ASGI —
  acceptable for the domain.
- **Neutral:** OpenAPI generated via drf-spectacular (tool choice confirmed in Phase 1).

## Compliance & security impact

Django's hardened defaults + `check --deploy` become part of the gate evidence. Admin is
permission-guarded, excluded from financial mutation paths.

## Reversibility

API layer is thin over application services; swapping/augmenting the HTTP layer later is
moderate cost. The domain layers are framework-free by construction.
