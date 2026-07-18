# Architecture Decision Records

Rules: sequential numbering; template in [`0000-template.md`](0000-template.md); create via
`/new-adr`. `Proposed` → `Accepted` requires human approval; accepted ADRs are immutable —
changes of direction are a new, superseding ADR.

| # | Title | Status |
|---|---|---|
| [0001](0001-modular-monolith.md) | Modular monolith first | Accepted |
| [0002](0002-django-primary-framework.md) | Django + DRF primary; FastAPI only by justification | Accepted |
| [0003](0003-postgresql-authority.md) | PostgreSQL sole authority for financial state | Accepted |
| [0004](0004-money-representation.md) | Money as integer minor units + ISO-4217 | Accepted |
| [0005](0005-multi-tenancy-model.md) | Database-per-tenant; separate control-plane DB | Accepted |
| [0006](0006-idempotency-design.md) | DB-arbitrated, scoped, hash-verified idempotency | Accepted |
| [0007](0007-transactional-outbox.md) | Transactional outbox + inbox deduplication | Accepted |
| [0008](0008-external-iam.md) | External IAM (OIDC; Keycloak reference) | Accepted |
| [0009](0009-worker-framework.md) | Celery (reliability-configured) as worker framework | Proposed |
