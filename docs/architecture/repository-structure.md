# Repository Structure

| | |
|---|---|
| **Purpose** | The target repository layout, materialized in Phase 1. Deviations require a documented rationale here. |
| **Audience** | Engineering. |
| **Owning phase** | Phase 0 (proposal) → Phase 1 (materialization). |
| **Related** | [Domain model](../domain/domain-model.md) · ADR-0001 · [Development workflow](../product/development-workflow.md) |

## Target layout (Phase 1)

```text
core-cbs/
  CLAUDE.md                      # Durable project-wide rules (exists)
  README.md                      # Entry point (exists)
  .claude/                       # Rules, agents, commands, hooks (exists)
  pyproject.toml                 # uv-managed; single source of deps & tool config
  uv.lock
  Makefile                       # lint / typecheck / format / test / check / docs / run
  compose.yaml                   # Dev stack: app, postgres:16, redis:7, keycloak (dev, `iam`
                                 # profile — wired in Phase 2)
  .pre-commit-config.yaml
  .github/workflows/             # ci.yml (lint+types+tests+docs+scans+compose smoke);
                                 # nightly.yml (concurrency+e2e) arrives in Phase 3
  src/
    next_core/
      platform/                  # Shared kernel: Money, ids, clock, TenantContext type,
                                 # event base classes, error taxonomy. Zero business policy.
      settings/                  # Django settings modules per profile (base/local/saas/onprem)
      control_plane/             # Tenant registry, profiles, entitlements, provisioning (SaaS only)
      tenancy/                   # Context resolution, DB routing, migration fan-out tooling
      iam/                       # OIDC boundary, permissions, maker-checker engine
      audit/                     # Append-only evidence store + write API
      parties/                   # Party registry, KYC references
      products/                  # Versioned products & plan bindings, activation workflow
      accounts/                  # Commercial accounts, lifecycle, blocks, account-number schemes,
                                 # account<->ledger mapping
      ledger/                    # ⚠️ Kernel: CoA, entries, postings, balances, periods,
                                 # posting service, idempotency, outbox, integrity
      transactions/              # Business operations, lifecycle, holds, orchestration
      pricing/                   # Fee plans & deterministic calculation
      limits/                    # Limit plans & atomic consumption
      interest/                  # Rate plans, accruals (Phase 8)
      reconciliation/            # Ingestion, matching, exceptions, adjustments (Phase 7)
      business_day/              # Business date, periods control, EoD orchestration (Phase 7)
      statements/                # Statement generation
      notifications/             # Outbox relay, webhook delivery & signing
      integrations/              # Extension adapters (statement sources, id schemes, …)
      reporting/                 # Trial balance, operational reports
  tests/
    unit/ property/ integration/ contract/ concurrency/ e2e/ performance/
    conftest.py                  # Real-PostgreSQL fixtures (Testcontainers/compose)
  docs/                          # This documentation tree (exists) + mkdocs.yml
  deploy/
    docker/                      # Dockerfile(s), image build config
    compose/                     # Reference compose deployments
    helm/                        # Helm chart for SaaS profiles
    onprem/                      # Offline bundle tooling, install/upgrade scripts, checksums
  scripts/                       # Operational & dev scripts (idempotent, documented)
```

### Per-context internal layout (uniform)

```text
next_core/<context>/
  domain/          # Entities, value objects, domain services, events — no Django imports
  application/     # Application services (use cases), unit-of-work boundaries
  models.py        # Django ORM models (persistence adapters)
  migrations/
  api/             # DRF views/serializers/routers for this context (versioned)
  admin.py         # Back-office (guarded; no financial mutation admin)
  apps.py
  ports.py         # Interfaces this context exposes to others (typed contracts)
```

**Boundary enforcement:** import-linter (or equivalent) contracts in CI encode the golden
dependency rules from the domain model — `ledger` imports only `platform`/`tenancy`; only
`transactions` imports `ledger.application.posting_service`; `control_plane` never imports
data-plane contexts; `platform` imports nothing of next_core.

## Deviations from the master-prompt §21 sketch (documented)

| Deviation | Rationale |
|---|---|
| No top-level `migrations/` dir | Django migrations live per-app (`<context>/migrations/`) — framework-native, per-context review. Fan-out tooling in `tenancy`. |
| Added `settings/` and `platform/` split | Profile-driven settings (ADR-0005/tenancy doc); explicit shared kernel keeps "platform" from becoming a dumping ground — zero-policy rule stated. |
| `.github/workflows/` added | CI is part of the engineering foundation (Phase 1 gate). |
| Repo root name `core-cbs` (not `next-core`) | GitHub repository already named `medext/core-cbs`; product name remains Next Core. |

## Current state (Phase 1)

Materialized: `CLAUDE.md`, `README.md`, `STATUS.md`, `.claude/`, `docs/` + `mkdocs.yml`,
`pyproject.toml`/`uv.lock`, `Makefile`, `compose.yaml`, `.github/workflows/ci.yml`,
`manage.py`, `deploy/docker/`, and under `src/next_core/`: `settings/` (base + local/saas/
onprem/test profiles), `platform/` (logging, telemetry, `health/` app), `urls.py`,
`wsgi.py`/`asgi.py`; `tests/unit/` + `tests/integration/`.

Bounded-context packages (`ledger/`, `transactions/`, `tenancy/`, …) are **not** created
ahead of their owning phase — no dead structure to drift. Each context appears with its
phase (tenancy/control_plane/iam/audit in Phase 2, ledger in Phase 3, …). Import-linter
boundary contracts land with the first multi-context phase (Phase 2).
