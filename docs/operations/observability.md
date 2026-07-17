# Observability & Operations *(skeleton — foundations Phase 1, authored Phase 9)*

| | |
|---|---|
| **Purpose** | Metrics, dashboards, alerts, and operational procedures. |
| **Owning phase** | Phase 1 (instrumentation foundation) → Phase 9 (dashboards/alerts) — same-change rule. |
| **Related** | [Runbooks](../runbooks/README.md) · master prompt §15 metric list |

## Fixed positions

- OpenTelemetry traces; Prometheus-compatible metrics; structured JSON logs with
  correlation/trace IDs; strict no-secrets/no-PII logging rules (`.claude/rules/security.md`).
- Tenant is a first-class dimension on every metric (bounded cardinality rules to define).

## Metric inventory to implement (target list, from master prompt §15)

Financial transaction throughput · posting latency · end-to-end API latency · error rate ·
rejection rate · insufficient-funds rate · idempotency replay rate · idempotency conflict
rate · DB lock wait · deadlocks · hot-account contention · outbox lag · queue lag · webhook
delivery failures · reconciliation exceptions · EoD duration · balance reconstruction
mismatches · tenant-level service health.

Each metric lands with the feature that produces it (same-change rule); the inventory table
here gains: name, type, labels, alert threshold, owning dashboard.

## To author in Phase 9

1. Dashboard catalog (platform, per-tenant health, ledger integrity, EoD, webhooks).
2. Alert definitions with severities & routing; alert→runbook links.
3. Incident classification (SEV levels, financial-integrity incidents are always SEV-1).
4. SLO definitions (only after Phase 9 benchmarks — see capacity model).
5. Ledger-integrity verification command reference & scheduling.
6. Tenant-isolation monitoring design.
