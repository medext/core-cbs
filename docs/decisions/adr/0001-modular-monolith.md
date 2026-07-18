# ADR-0001 — Modular monolith first, microservice extraction later only if proven necessary

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** mohamed@next.mr — approved 2026-07-18 (Phase 0 gate)

## Context

Next Core must be bank-grade (correctness, atomicity, auditability) yet operable by a
medium-sized engineering organization, and deployable identically as SaaS and on-premise —
including air-gapped installs where a service mesh is a liability. The most dangerous
architectural failure mode for a ledger is a distributed transaction across services: the
double-entry invariants (balanced entries, atomic funds checks, idempotency) are trivial in
one PostgreSQL transaction and research-grade problems across service boundaries.

## Decision

We will build Next Core as a **modular monolith**: one deployable Django application composed
of strictly bounded contexts (see domain model) with enforced import contracts, explicit
application-service interfaces, domain events over a transactional outbox, and per-context
persistence models. Financial writes are synchronous, single-database transactions.
Service extraction remains possible at context seams (the posting service and event contracts
are the stable interfaces) but requires a future ADR with a formal consistency design.

## Alternatives considered

- **Microservices from the start** — rejected: forces distributed consistency into the ledger
  (sagas/2PC for transfers), multiplies operational surface for on-premise customers, and
  exceeds the operating capacity assumption. The master prompt prohibits it absent proof.
- **Unstructured monolith (plain Django apps, shared models)** — rejected: guarantees
  entanglement of ledger with business policy; makes future extraction impossible and review
  boundaries meaningless.
- **Two services from day one (ledger service + app)** — rejected for now: splitting the
  ledger from transaction orchestration before proving the distributed model is safe is
  explicitly prohibited (§4.2); revisit only with a formal consistency design.

## Consequences

- **Positive:** invariants enforceable in single DB transactions; one artifact for all
  editions; simple on-prem installs; smaller attack/ops surface; fast local dev.
- **Negative / accepted costs:** discipline is required to keep boundaries real —
  mitigated by import-linter contracts in CI, per-context layout, and the
  `core-banking-architect` reviewer; scaling is per-process + per-tenant-DB, not per-context.
- **Neutral / follow-ups:** FastAPI side-services allowed only via future ADR for genuinely
  isolated boundaries (ingestion gateway, etc.).

## Compliance & security impact

Fewer network trust boundaries; the threat model concentrates on the app↔DB and app↔IAM
boundaries. Audit trail lives in one transactional domain.

## Reversibility

Medium cost by design: contexts are extraction-ready seams. The ledger stays in-process with
transaction orchestration until a formal consistency ADR proves otherwise.
