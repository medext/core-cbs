# Architecture Decision Records

Rules: sequential numbering; template in [`0000-template.md`](0000-template.md); create via
`/new-adr`. `Proposed` → `Accepted` requires human approval; accepted ADRs are immutable —
changes of direction are a new, superseding ADR.

| # | Title | Status |
|---|---|---|
| [0001](0001-modular-monolith.md) | Modular monolith first | Proposed |
| [0002](0002-django-primary-framework.md) | Django + DRF primary; FastAPI only by justification | Proposed |
| [0003](0003-postgresql-authority.md) | PostgreSQL sole authority for financial state | Proposed |
| [0004](0004-money-representation.md) | Money as integer minor units + ISO-4217 | Proposed |
| [0005](0005-multi-tenancy-model.md) | Database-per-tenant; separate control-plane DB | Proposed |
| [0006](0006-idempotency-design.md) | DB-arbitrated, scoped, hash-verified idempotency | Proposed |
| [0007](0007-transactional-outbox.md) | Transactional outbox + inbox deduplication | Proposed |
| [0008](0008-external-iam.md) | External IAM (OIDC; Keycloak reference) | Proposed |
