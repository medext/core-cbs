# ADR-0005 — Database-per-tenant for financial data; separate control-plane database

- **Status:** Proposed (Phase 0 review)
- **Date:** 2026-07-17
- **Deciders:** pending human approval

## Context

Invariant 14 (cross-tenant access impossible) + PRD editions: shared SaaS, dedicated SaaS,
on-premise/air-gapped from one codebase. Regulated financial records favor strong isolation
(master prompt §10). Tenant counts are expected in the tens-to-hundreds (institutions), not
millions — isolation weight is affordable.

## Decision

- **Financial data plane: one PostgreSQL database per tenant.** All ledger, account,
  transaction, audit, and outbox data for a tenant lives in its own database with isolated
  connection pools and per-tenant encryption/backup/residency options.
- **Control plane: its own database**, storing only registry/routing/entitlement/operational
  metadata — never financial data; no runtime connection from control plane to tenant DBs.
- **Tenant context is explicit everywhere; resolution failure is fatal; no default tenant.**
- **On-premise = the same model with exactly one tenant DB and a static registry** (control
  plane absent at runtime).

## Alternatives considered

- **Row-level (shared tables + `tenant_id`)** — rejected for financial data: a single missing
  WHERE clause or ORM manager bypass is a cross-tenant breach; noisy-neighbor and per-tenant
  restore are hard; regulator conversations are harder. (Acceptable for nothing in the data
  plane; control-plane tables are vendor-scoped, not tenant-shared financial data.)
- **Schema-per-tenant (one DB, many schemas)** — rejected: shares the failure domain,
  credentials surface, and maintenance windows of one DB while keeping ~all the fan-out
  burden (per-schema migrations); per-tenant PITR restore still awkward.
- **Cluster-per-tenant** — rejected as default: operational overkill for small tenants;
  effectively available anyway as the dedicated-SaaS profile.

## Consequences

- **Positive:** physical blast-radius containment; per-tenant backup/restore/PITR, residency,
  key management, migration windows; simple air-gap story; deterministic routing is auditable.
- **Negative / accepted costs:** connection-pool management across N databases (per-tenant
  pools, bounded; pooler evaluation in Phase 9); migration fan-out (resumable runner with
  per-tenant status, N-1 compatibility discipline); higher infra floor per tenant (accepted —
  tenants are institutions); cross-tenant analytics only via per-tenant export pipelines.
- **Neutral:** provisioning automation (create DB, bootstrap schema, register routing) is a
  Phase 2 deliverable; pool/pooler specifics decided with real numbers (OD-10).

## Compliance & security impact

Strongest available isolation posture short of dedicated clusters; per-tenant keys and
backups map cleanly to institutional requirements; the control-plane/no-financial-access rule
becomes physically enforceable (no credentials held).

## Reversibility

Moving *down* to shared-schema later would be a data-consolidation program (unlikely to be
wanted). Moving specific tenants *up* to dedicated clusters is cheap by construction.
